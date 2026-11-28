"""Compose the server's concrete dependencies and run its HTTP application."""

from flask import Flask
from werkzeug.serving import WSGIRequestHandler

from pdf2zh_server.api import ServerApi
from pdf2zh_server.engines.wenyi.adapter import WenyiAdapter
from pdf2zh_server.engines.wenyi.paths import WenyiPaths
from pdf2zh_server.engines.wenyi.runtime import ManagedWenyiRuntime
from pdf2zh_server.environment.discovery import ENGINE_ENV_NAMES
from pdf2zh_server.environment.manager import VirtualEnvManager
from pdf2zh_server.environment.updates import server_version_from_source
from pdf2zh_server.paths import ServerPaths
from pdf2zh_server.pdf.cropper import Cropper
from pdf2zh_server.tasks.manager import TaskManager
from pdf2zh_server.tasks.service import TranslationService


class _QuietAccessHandler(WSGIRequestHandler):
    _SILENT_PREFIXES = ("/api/tasks", "/api/history", "/events", "/health", "/favicon")

    def log_request(self, code="-", size="-"):
        path = (getattr(self, "path", None) or "").split("?", 1)[0]
        if any(
            (
                path == prefix or path.startswith(prefix + "/")
                for prefix in self._SILENT_PREFIXES
            )
        ):
            return
        super().log_request(code, size)


class ServerApplication:
    def __init__(self, options, version=None, paths=None, task_manager=None):
        self.options = options
        self.paths = paths or ServerPaths()
        self.app = Flask(
            __name__, static_folder=str(self.paths.web), static_url_path="/assets"
        )
        manager = None
        if options.enable_venv:
            manager = VirtualEnvManager(
                self.paths.config_paths["venv"],
                ENGINE_ENV_NAMES.copy(),
                options.env_tool,
                options.enable_mirror,
                options.skip_install,
                options.mirror_source,
            )
        wenyi_paths = WenyiPaths.resolve(
            getattr(options, "wenyi_data_dir", None),
            getattr(options, "wenyi_cache_dir", None),
        )
        wenyi_python = getattr(options, "wenyi_python", None)
        wenyi_bridge_url = getattr(options, "wenyi_bridge_url", None)
        runtime = (
            ManagedWenyiRuntime(
                manager,
                wenyi_paths.runtime,
                session_root=wenyi_paths.sessions,
                cache_root=wenyi_paths.cache,
                bridge_url=wenyi_bridge_url,
            )
            if options.enable_venv and not wenyi_python
            else None
        )
        wenyi = WenyiAdapter(
            wenyi_paths.tasks,
            self.paths.output,
            state_root=wenyi_paths.translations,
            cache_root=wenyi_paths.cache,
            python=wenyi_python,
            bridge_url=wenyi_bridge_url or "http://127.0.0.1:8765",
            timeout=getattr(options, "wenyi_timeout", 10800),
            runtime=runtime,
        )
        self.service = TranslationService(
            options,
            self.paths,
            task_manager or TaskManager(),
            manager,
            Cropper(),
            wenyi=wenyi,
        )
        self.api = ServerApi(
            self.app,
            self.service,
            options,
            self.paths,
            version or server_version_from_source(),
        )

    def run(self, host, port, debug=False):
        print(f"🌐 Server将启动在: http://{host}:{port}")
        print(f"📊 翻译进度监控页面: http://localhost:{port}/")
        print(f"💡 健康检查端点: http://localhost:{port}/health")
        try:
            self.app.run(
                host=host,
                port=port,
                debug=debug,
                threaded=True,
                request_handler=_QuietAccessHandler,
            )
        finally:
            self.service.wenyi.close()
