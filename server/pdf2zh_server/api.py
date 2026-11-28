"""Existing HTTP routes and JSON/SSE protocol adapters."""

import json
import os
import re
import time
import traceback

from flask import Response, jsonify, request, send_file

from pdf2zh_server.configuration.storage import clear_saved_credential
from pdf2zh_server.pdf.tables.mode import TABLE_MODES
from pdf2zh_server.providers.models import fetch_model_ids
from pdf2zh_server.providers.relay_options import parse_api_format
from pdf2zh_server.providers.request_headers import (
    build_request_headers,
    parse_extra_headers,
)

pdf2zh_next = "pdf2zh_next"


class ServerApi:
    def __init__(self, app, service, options, paths, version):
        self.app = app
        self.service = service
        self.options = options
        self.paths = paths
        self.version = version
        self.setup_routes()

    def setup_routes(self):
        self.app.add_url_rule("/", "index", self.index)
        self.app.add_url_rule(
            "/translate", "translate", self.translate, methods=["POST"]
        )
        self.app.add_url_rule("/crop", "crop", self.crop, methods=["POST"])
        self.app.add_url_rule(
            "/crop-compare", "crop-compare", self.crop_compare, methods=["POST"]
        )
        self.app.add_url_rule("/compare", "compare", self.compare, methods=["POST"])
        self.app.add_url_rule(
            "/translatedFile/<path:filename>",
            "download",
            self.download_file,
            methods=["GET", "HEAD"],
        )
        self.app.add_url_rule(
            "/translatedInfo", "translated_info", self.translated_info, methods=["GET"]
        )
        self.app.add_url_rule("/health", "health", self.health_check)
        self.app.add_url_rule("/events", "events", self.events)
        self.app.add_url_rule("/api/history", "history", self.get_history)
        self.app.add_url_rule("/api/tasks", "tasks", self.get_tasks)
        self.app.add_url_rule(
            "/api/task/cancel", "task_cancel", self.task_cancel, methods=["POST"]
        )
        self.app.add_url_rule("/api/config", "config", self.get_config)
        self.app.add_url_rule(
            "/api/llm-api/clear", "llm_api_clear", self.llm_api_clear, methods=["POST"]
        )
        self.app.add_url_rule(
            "/api/llm-api/models",
            "llm_api_models",
            self.llm_api_models,
            methods=["POST"],
        )
        self.app.add_url_rule("/favicon.svg", "favicon", self.favicon)
        self.app.add_url_rule("/bo.mp3", "notification_sound", self.notification_sound)

    def health_check(self):
        return (
            jsonify(
                {
                    "status": "ok",
                    "version": self.version,
                    "message": "PDF2zh Server is running",
                    "outputDir": os.path.abspath(str(self.paths.output)),
                    "tableModes": list(TABLE_MODES),
                    "referenceSkip": True,
                    "deepseekFlashThinkingPatch": True,
                    "relayPatch": True,
                    "relayPatchVersion": 2,
                }
            ),
            200,
        )

    def index(self):
        try:
            index_path = os.path.join(str(self.paths.web), "index.html")
            if os.path.exists(index_path):
                return send_file(index_path)
            else:
                return (
                    jsonify({"status": "error", "message": "index.html not found"}),
                    404,
                )
        except Exception as e:
            return (jsonify({"status": "error", "message": str(e)}), 500)

    def events(self):

        def generate():
            while True:
                try:
                    tasks_data = {
                        "type": "tasks",
                        "data": self.service.tasks.get_active_tasks_list(),
                    }
                    yield f"data: {json.dumps(tasks_data)}\n\n"
                    time.sleep(1)
                except GeneratorExit:
                    break

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
        )

    def get_history(self):
        return jsonify(
            {"status": "success", "history": self.service.tasks.get_history()}
        )

    def task_cancel(self):
        data = request.get_json(silent=True) or {}
        task_id = str(data.get("taskId") or "").strip()
        if not task_id:
            return (jsonify({"status": "error", "message": "taskId is required"}), 400)
        task = self.service.tasks.get_task(task_id)
        if not task:
            return (jsonify({"status": "error", "message": "task not found"}), 404)
        if task.get("engine") != "wenyi":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "当前引擎暂不支持取消。",
                    }
                ),
                400,
            )
        cancelled = self.service.tasks.cancel_task(task_id)
        return (
            jsonify(
                {
                    "status": "success" if cancelled else "error",
                    "message": "已取消" if cancelled else "任务已结束, 无法取消",
                }
            ),
            200 if cancelled else 409,
        )

    def get_tasks(self):
        return jsonify(
            {"status": "success", "tasks": self.service.tasks.get_active_tasks_list()}
        )

    def get_config(self):
        config_info = {
            "version": self.version,
            "port": self.options.port,
            "enable_venv": self.options.enable_venv,
            "env_tool": self.options.env_tool,
            "enable_mirror": self.options.enable_mirror,
            "mirror_source": self.options.mirror_source
            if self.options.enable_mirror
            else "-",
            "skip_install": self.options.skip_install,
            "enable_winexe": self.options.enable_winexe,
        }
        return jsonify({"status": "success", "config": config_info})

    def llm_api_clear(self):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return (
                jsonify({"status": "error", "message": "Invalid JSON request"}),
                400,
            )
        service = str(data.get("service") or "").strip()
        if not service:
            return (jsonify({"status": "error", "message": "service is required"}), 400)
        try:
            cleared = clear_saved_credential(
                self.paths.config_paths[pdf2zh_next], service
            )
        except Exception as exc:
            print(f"⚠️ 清除 {service} 保存的密钥失败: {exc}")
            cleared = False
        print(f"🧹 /api/llm-api/clear service={service} cleared={cleared}")
        return (
            jsonify(
                {
                    "status": "success",
                    "service": service,
                    "cleared": [pdf2zh_next] if cleared else [],
                }
            ),
            200,
        )

    def llm_api_models(self):
        from urllib.error import HTTPError, URLError
        from urllib.parse import urlsplit

        from pdf2zh_server.providers.models import model_list_url

        try:
            data = request.get_json()
            extra_data = data.get("extraData") or {}
            api_format = parse_api_format(extra_data.get("zotero_api_format"))
            custom_headers = parse_extra_headers(extra_data.get("zotero_extra_headers"))
            api_key = data.get("apiKey", "")
            auth_mode = extra_data.get("zotero_auth_mode", "auto")
            request_headers = build_request_headers(
                api_format, api_key, custom_headers, auth_mode=auth_mode
            )
            service = data.get("service", "")
            model_url = model_list_url(data.get("apiUrl", ""), service, api_format)
            if service == "gemini" and auth_mode == "auto":
                compatible = re.search("/openai(?:/|$)", urlsplit(model_url).path)
                automatic_name = (
                    "x-api-key" if api_format == "messages" else "authorization"
                )
                custom_names = {name.lower() for name in custom_headers}
                request_headers = {
                    name: value
                    for name, value in request_headers.items()
                    if name.lower() != automatic_name or automatic_name in custom_names
                }
                credential_name = "Authorization" if compatible else "x-goog-api-key"
                if credential_name.lower() not in custom_names:
                    request_headers[credential_name] = (
                        f"Bearer {api_key}" if compatible else api_key
                    )
            models = fetch_model_ids(
                data.get("apiUrl", ""),
                request_headers,
                service=service,
                api_format=api_format,
                api_key=api_key,
            )
            return jsonify({"status": "success", "models": models})
        except HTTPError as exc:
            messages = {
                401: "模型接口认证失败，请检查 Key 和认证请求头。",
                403: "当前凭据没有访问模型目录的权限。",
                404: "模型目录不存在，请检查 URL；服务商未开放目录时可手动填写模型。",
                429: "模型接口请求过于频繁或额度不足，请稍后重试。",
            }
            message = messages.get(exc.code, "模型接口返回错误，请检查服务商状态。")
            return (
                jsonify({"status": "error", "message": f"HTTP {exc.code}：{message}"}),
                exc.code,
            )
        except json.JSONDecodeError:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "模型接口未返回 JSON，请检查 URL 是否指向 API 地址。",
                    }
                ),
                502,
            )
        except TimeoutError:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "连接模型接口超时，请检查网络或代理设置。",
                    }
                ),
                504,
            )
        except (URLError, OSError):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "无法连接模型接口，请检查 URL、网络或代理设置。",
                    }
                ),
                502,
            )
        except Exception as exc:
            return (jsonify({"status": "error", "message": str(exc)}), 400)

    def favicon(self):
        favicon_path = os.path.join(str(self.paths.web / "assets"), "favicon.svg")
        if os.path.exists(favicon_path):
            return send_file(favicon_path, mimetype="image/svg+xml")
        return ("", 404)

    def notification_sound(self):
        sound_path = os.path.join(str(self.paths.web / "assets"), "bo.mp3")
        if os.path.exists(sound_path):
            return send_file(sound_path, mimetype="audio/mpeg")
        return ("", 404)

    def translated_info(self):
        try:
            stem = (request.args.get("stem") or "").strip()
            base = os.path.abspath(str(self.paths.output))
            files = []
            if os.path.isdir(base):
                for name in os.listdir(base):
                    if not name.lower().endswith(".pdf"):
                        continue
                    if stem and (
                        not (
                            name.startswith(stem + "-")
                            or name.startswith(stem + ".")
                            or name.startswith(stem + "_")
                        )
                    ):
                        continue
                    full = os.path.abspath(os.path.join(base, name))
                    try:
                        if os.path.commonpath([base, full]) != base:
                            continue
                    except ValueError:
                        continue
                    if not os.path.isfile(full):
                        continue
                    files.append(
                        {
                            "fileName": name,
                            "filePath": full,
                            "size": os.path.getsize(full),
                            "mtime": os.path.getmtime(full),
                        }
                    )
            files.sort(key=lambda item: item["mtime"], reverse=True)
            return (jsonify({"status": "ok", "outputDir": base, "files": files}), 200)
        except Exception as e:
            traceback.print_exc()
            return (jsonify({"status": "error", "message": str(e)}), 500)

    def download_file(self, filename):
        try:
            filename = os.path.basename(filename or "")
            if not filename or filename in {".", ".."}:
                return (jsonify({"status": "error", "message": "Invalid path"}), 400)
            base = os.path.abspath(str(self.paths.output))
            full = os.path.abspath(os.path.join(str(self.paths.output), filename))
            if os.path.commonpath([base, full]) != base:
                return (jsonify({"status": "error", "message": "Invalid path"}), 400)
            if os.path.exists(full):
                is_preview = request.args.get("preview") == "true"
                return send_file(full, as_attachment=not is_preview)
            return (
                jsonify({"status": "error", "message": f"File not found: {filename}"}),
                404,
            )
        except Exception as e:
            traceback.print_exc()
            return (jsonify({"status": "error", "message": str(e)}), 500)

    @staticmethod
    def _truthy_flag(value):
        if value is True:
            return True
        if value is False or value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "async", "accepted"}

    def _client_wants_async_job(self):
        header = (request.headers.get("X-PDF2zh-Protocol") or "").strip().lower()
        if header in {"accepted", "async"}:
            return True
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return False
        if "asyncJob" in data:
            return self._truthy_flag(data.get("asyncJob"))
        protocol = str(data.get("clientProtocol") or "").strip().lower()
        return protocol in {"accepted", "async"}

    def translate(self):
        return self.service.translate(
            request.get_json(silent=True), async_job=self._client_wants_async_job()
        )

    def crop(self):
        return self.service.crop(request.get_json(silent=True))

    def crop_compare(self):
        return self.service.crop_compare(
            request.get_json(silent=True), async_job=self._client_wants_async_job()
        )

    def compare(self):
        return self.service.compare(
            request.get_json(silent=True), async_job=self._client_wants_async_job()
        )
