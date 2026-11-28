#!/usr/bin/env python3
"""Translate a Finder-selected PDF through the project's main Server."""

import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = PROJECT_ROOT / "server"
sys.path.insert(0, str(SERVER_ROOT))

from pdf2zh_server.providers.catalog import (
    pdf2zh_next_config_map,
    pdf2zh_next_service_aliases,
)

LEGACY_FIELD_ALIASES = {
    "deepl": {"apiKey": "DEEPL_AUTH_KEY"},
    "qwen-mt": {"apiKey": "ALI_API_KEY", "model": "ALI_MODEL"},
    "tencent": {
        "apiKey": "TENCENTCLOUD_SECRET_KEY",
        "model": "TENCENTCLOUD_SECRET_ID",
    },
}


def _saved_config_value(service, values, field, next_fields):
    legacy_key = LEGACY_FIELD_ALIASES.get(service, {}).get(field)
    if not legacy_key:
        prefix = service.upper().replace("-", "_")
        suffixes = {
            "apiKey": ("API_KEY", "AUTH_KEY", "SECRET_KEY"),
            "apiUrl": ("BASE_URL", "API_URL", "ENDPOINT", "URL", "HOST"),
            "model": ("MODEL",),
        }[field]
        legacy_key = next(
            (
                f"{prefix}_{suffix}"
                for suffix in suffixes
                if f"{prefix}_{suffix}" in values
            ),
            "",
        )
    next_key = next_fields.get(field, "")
    return values.get(legacy_key, values.get(next_key.upper(), ""))


class PDFTranslatorClient:
    def __init__(self, server_url="http://localhost:8888"):
        self.server_url = server_url.rstrip("/")
        self.configuration_path = Path(__file__).with_name("config.json")
        self.task_timeout = 10800

    def send_notification(self, title, message):
        if shutil.which("terminal-notifier"):
            command = [
                "terminal-notifier", "-title", title, "-message", message,
                "-group", "pdf-translate-quickaction",
            ]
        else:
            command = [
                "osascript", "-e",
                f"display notification {json.dumps(message, ensure_ascii=False)} "
                f"with title {json.dumps(title, ensure_ascii=False)}",
            ]
        try:
            subprocess.run(command, check=False, capture_output=True)
        except OSError as exc:
            print(f"通知发送失败: {exc}")

    def _request_json(self, path, data=None):
        request = Request(
            self.server_url + path,
            data=json.dumps(data).encode("utf-8") if data is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            error = json.load(exc)
            raise RuntimeError(error.get("message", str(exc))) from exc

    def is_server_running(self):
        try:
            return self._request_json("/health").get("status") == "ok"
        except (OSError, URLError, ValueError, RuntimeError):
            return False

    def start_server(self):
        self.send_notification("PDF 翻译", "正在启动翻译服务...")
        result = subprocess.run(
            ["/bin/bash", str(Path(__file__).with_name("start_server.sh")), "start"],
            env={
                **os.environ,
                "ZOTERO_PDF2ZH_ROOT": str(PROJECT_ROOT),
                "ZOTERO_PDF2ZH_PYTHON": sys.executable,
            },
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stdout or result.stderr or "翻译服务启动失败")
        for _ in range(30):
            time.sleep(1)
            if self.is_server_running():
                self.send_notification("PDF 翻译", "翻译服务已启动")
                return
        raise RuntimeError(f"翻译服务启动失败，请查看 {PROJECT_ROOT / 'logs' / 'server.log'}。")

    def build_request(self, pdf_path):
        configuration_path = self.configuration_path
        if not configuration_path.exists():
            configuration_path = SERVER_ROOT / "config" / "config.json"
        configuration = {}
        if configuration_path.exists():
            configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
        translator = configuration.get("translators", [{}])[0]
        stored_service = translator.get("name", "deepseek")
        service = pdf2zh_next_service_aliases.get(stored_service, stored_service)
        fields = pdf2zh_next_config_map.get(service, {})
        values = translator.get("envs", {})
        next_api_key = fields.get("apiKey", "")
        legacy_prefix = stored_service.upper().replace("-", "_").lower()
        if stored_service == "qwen-mt":
            legacy_prefix = "ali"
        next_prefix = next_api_key.removesuffix("_api_key")
        extra_data = {}
        for key in fields.get("extraData", []):
            value = values.get(key, values.get(key.upper()))
            if (
                value is None
                and legacy_prefix
                and key.startswith(f"{next_prefix}_")
            ):
                legacy_key = legacy_prefix + key[len(next_prefix) :]
                value = values.get(legacy_key.upper())
            if value is not None:
                extra_data[key] = value

        api_configuration = {
            "service": service,
            "apiKey": _saved_config_value(stored_service, values, "apiKey", fields),
            "apiUrl": _saved_config_value(stored_service, values, "apiUrl", fields),
            "model": _saved_config_value(stored_service, values, "model", fields),
            "extraData": extra_data,
        }
        return {
            "fileName": pdf_path.name,
            "fileContent": base64.b64encode(pdf_path.read_bytes()).decode("ascii"),
            "engine": "pdf2zh_next",
            "next_service": service,
            "service": service,
            "qps": 4,
            "sourceLang": "en",
            "targetLang": "zh",
            "asyncJob": True,
            "llm_api": api_configuration,
        }

    def wait_for_task(self, task_id, file_name):
        deadline = time.monotonic() + self.task_timeout
        notified = set()
        while time.monotonic() < deadline:
            tasks = self._request_json("/api/tasks").get("tasks", [])
            task = next((item for item in tasks if item.get("taskId") == task_id), None)
            if task is None:
                history = self._request_json("/api/history").get("history", [])
                task = next((item for item in history if item.get("taskId") == task_id), None)
            if task is not None:
                status = task.get("status")
                if status in {"failed", "cancelled", "失败", "已取消"}:
                    raise RuntimeError(task.get("error") or task.get("message") or "翻译失败")
                if status in {"success", "完成"}:
                    return task.get("result") or task
                progress = task.get("progress") or 0
                for milestone in (25, 50, 75, 90):
                    if progress >= milestone and milestone not in notified:
                        self.send_notification("PDF 翻译进度", f"{file_name}：{milestone}%")
                        notified.add(milestone)
            time.sleep(1)
        raise RuntimeError("翻译任务等待超时，请查看主 Server 的任务记录。")

    def translate_pdf(self, pdf_path):
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"文件不存在: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError("只支持 PDF 文件")
        if not self.is_server_running():
            self.start_server()
        self.send_notification("PDF 翻译开始", f"正在翻译: {pdf_path.name}")
        result = self._request_json("/translate", self.build_request(pdf_path))
        if result.get("status") == "accepted":
            result = self.wait_for_task(result["taskId"], pdf_path.name)
        if result.get("status") == "error":
            raise RuntimeError(result.get("message", "翻译失败"))
        dual_file = next(
            (name for name in result.get("fileList", [])
             if "dual" in name.lower() and name.lower().endswith(".pdf")),
            None,
        )
        if dual_file is None:
            raise RuntimeError("翻译完成但未返回双语 PDF，请查看主 Server 的任务记录。")
        target = pdf_path.with_name(f"{pdf_path.stem}-dual.pdf")
        with urlopen(self.server_url + "/translatedFile/" + quote(dual_file), timeout=60) as response:
            target.write_bytes(response.read())
        self.send_notification("PDF 翻译完成", f"已生成: {target.name}")
        subprocess.run(["open", "-R", str(target)], check=False)
        return str(target)


def main():
    if len(sys.argv) < 2:
        print("用法: python translate_pdf_client.py <pdf_file_path>")
        return 1
    client = PDFTranslatorClient()
    try:
        print(f"翻译成功: {client.translate_pdf(sys.argv[1])}")
        return 0
    except Exception as exc:
        print(f"错误: {exc}")
        client.send_notification("PDF 翻译失败", str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
