import base64
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    "translation_client", Path(__file__).resolve().parents[1] / "translate_pdf_client.py"
)
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)


class TranslationClientTests(unittest.TestCase):
    def test_auto_start_reuses_the_shared_process_lifecycle(self):
        client = client_module.PDFTranslatorClient()
        client.send_notification = Mock()
        client.is_server_running = Mock(side_effect=[False, True])
        started = client_module.subprocess.CompletedProcess([], 0, "started", "")
        with patch.object(client_module.subprocess, "run", return_value=started) as launch, \
                patch.object(client_module.time, "sleep"):
            client.start_server()
        self.assertEqual(launch.call_args.args[0], [
            "/bin/bash", str(Path(client_module.__file__).with_name("start_server.sh")), "start",
        ])
        self.assertEqual(
            launch.call_args.kwargs["env"]["ZOTERO_PDF2ZH_PYTHON"],
            client_module.sys.executable,
        )
        self.assertEqual(client.is_server_running.call_count, 2)

    def test_start_failure_reports_the_shared_launcher_error(self):
        client = client_module.PDFTranslatorClient()
        client.send_notification = Mock()
        client.is_server_running = Mock()
        failed = client_module.subprocess.CompletedProcess([], 1, "端口 8888 已被占用", "")
        with patch.object(client_module.subprocess, "run", return_value=failed), \
                self.assertRaisesRegex(RuntimeError, "端口 8888 已被占用"):
            client.start_server()
        client.is_server_running.assert_not_called()

    def test_existing_automation_config_becomes_a_main_server_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"offline PDF content")
            configuration = root / "config.json"
            configuration.write_text(json.dumps({
                "translators": [{
                    "name": "openailiked",
                    "envs": {
                        "OPENAILIKED_API_KEY": "offline-key",
                        "OPENAILIKED_BASE_URL": "https://provider.invalid/v1",
                        "OPENAILIKED_MODEL": "offline-model",
                        "OPENAILIKED_TIMEOUT": "45",
                        "custom_parameter": 3,
                    },
                }],
            }), encoding="utf-8")
            original = configuration.read_bytes()
            client = client_module.PDFTranslatorClient()
            client.configuration_path = configuration
            request = client.build_request(pdf)
            self.assertEqual(request["engine"], "pdf2zh_next")
            self.assertEqual(request["next_service"], "openaicompatible")
            self.assertTrue(request["asyncJob"])
            self.assertEqual(base64.b64decode(request["fileContent"]), pdf.read_bytes())
            self.assertEqual(request["llm_api"]["apiKey"], "offline-key")
            self.assertEqual(request["llm_api"]["apiUrl"], "https://provider.invalid/v1")
            self.assertEqual(request["llm_api"]["model"], "offline-model")
            self.assertEqual(
                request["llm_api"]["extraData"]["openai_compatible_timeout"], "45"
            )
            self.assertNotIn("custom_parameter", request["llm_api"]["extraData"])
            self.assertEqual(configuration.read_bytes(), original)

    def test_accepted_job_uses_history_and_downloads_the_returned_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "paper.pdf"
            pdf.write_bytes(b"source PDF")
            client = client_module.PDFTranslatorClient()
            client.is_server_running = Mock(return_value=True)
            client.build_request = Mock(return_value={"fileName": "paper.pdf"})
            client.send_notification = Mock()
            replies = iter([
                {"status": "accepted", "taskId": "job-1"},
                {"tasks": [{"taskId": "job-1", "progress": 25, "status": "翻译中"}]},
                {"tasks": []},
                {"history": [{
                    "taskId": "job-1", "status": "success",
                    "fileList": ["server-renamed.LR_dual.pdf"],
                }]},
            ])
            client._request_json = Mock(side_effect=lambda *args: next(replies))
            with patch.object(client_module.time, "sleep"), \
                    patch.object(client_module, "urlopen", return_value=io.BytesIO(b"translated PDF")) as download, \
                    patch.object(client_module.subprocess, "run") as finder:
                target = Path(client.translate_pdf(pdf))
            self.assertEqual(target, pdf.with_name("paper-dual.pdf"))
            self.assertEqual(target.read_bytes(), b"translated PDF")
            self.assertIn("server-renamed.LR_dual.pdf", download.call_args.args[0])
            finder.assert_called_once_with(["open", "-R", str(target)], check=False)
            self.assertEqual(client._request_json.call_args_list[-1].args[0], "/api/history")
            self.assertTrue(any("25%" in call.args[1] for call in client.send_notification.call_args_list))

    def test_failed_task_preserves_the_server_error(self):
        client = client_module.PDFTranslatorClient()
        client._request_json = Mock(return_value={"tasks": [{
            "taskId": "failed-job", "status": "失败", "error": "Provider rejected the model",
        }]})
        with self.assertRaisesRegex(RuntimeError, "Provider rejected the model"):
            client.wait_for_task("failed-job", "paper.pdf")


if __name__ == "__main__":
    unittest.main()
