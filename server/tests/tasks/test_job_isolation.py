import base64
import contextlib
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pdf2zh_server.application as server
import toml
import fitz
from pdf2zh_server.configuration.request import Config
from pdf2zh_server.configuration.storage import clear_saved_credential
from pdf2zh_server.tasks.workspace import JobWorkspace
from pdf2zh_server.providers.relay_patch import load_relay_options
from pdf2zh_server.tasks.manager import TaskManager
from pdf2zh_server.configuration.storage import update_config_file

from pdf2zh_server.paths import ServerPaths
from pdf2zh_server.pdf.outputs import get_filetype
from pdf2zh_server.engines import next as next_engine
from pdf2zh_server.configuration import storage as configuration_storage


class JobIsolationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="pdf2zh-job-test-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.published = self.root / "published"
        self.published.mkdir()
        (self.root / "config").mkdir()
        self.saved = self.root / "config" / "config.toml"
        self.saved.write_text("", encoding="utf-8")
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch("builtins.print"))
        self.application = server.ServerApplication(
            SimpleNamespace(
                enable_venv=False,
                enable_winexe=False,
                winexe_path="",
                wenyi_data_dir=str(self.root / "wenyi-data"),
                wenyi_cache_dir=str(self.root / "wenyi-cache"),
            ),
            paths=ServerPaths(self.root, self.published),
            task_manager=TaskManager(),
        )
        self.translator = self.application.service
        self.client = self.application.app.test_client()

    @staticmethod
    def request(name="paper.pdf", content=b"%PDF-1.7\nsource\n%%EOF", tenant="a"):
        return {
            "engine": "pdf2zh_next",
            "next_service": f"relay-{tenant}",
            "fileName": name,
            "fileContent": base64.b64encode(content).decode(),
            "mono": True,
            "dual": False,
            "noDual": True,
            "llm_api": {
                "service": f"relay-{tenant}",
                "apiUrl": f"https://{tenant}.example/v1",
                "apiKey": f"synthetic-{tenant}",
                "model": "same-model",
                "extraData": {
                    "zotero_api_format": "responses" if tenant == "a" else "messages",
                    "zotero_extra_headers": {"X-Tenant": tenant},
                },
            },
        }

    @staticmethod
    def fake_outputs(command, content=None):
        input_path = Path(command[1])
        output = Path(command[command.index("--output") + 1])
        lang = command[command.index("--lang-out") + 1]
        body = input_path.read_bytes() if content is None else content
        paths = []
        for kind, omitted in (("mono", "--no-mono"), ("dual", "--no-dual")):
            if omitted not in command:
                path = output / f"{input_path.stem}.no_watermark.{lang}.{kind}.pdf"
                path.write_bytes(body)
                paths.append(path)
        return paths

    def assert_no_workspaces(self):
        jobs = self.published / ".jobs"
        self.assertEqual(list(jobs.iterdir()) if jobs.exists() else [], [])

    def test_same_filename_parallel_jobs_keep_input_config_headers_and_output_isolated(
        self,
    ):
        inputs = {}
        configs = {}
        for tenant in ("a", "b"):
            directory = self.root / tenant
            directory.mkdir()
            inputs[tenant] = directory / "paper.pdf"
            inputs[tenant].write_bytes(f"%PDF-1.7\nsource-{tenant}\n%%EOF".encode())
            configs[tenant] = Config(self.request(tenant=tenant))

        barrier = threading.Barrier(2)
        records, results, errors = {}, {}, []

        def execute(command, task_id, _args, _environment, **_callbacks):
            snapshot = Path(command[command.index("--config-file") + 1])
            sidecar = Path(command[command.index("--zotero-relay-patch") + 1])
            # Both jobs have updated the persistent file before either engine
            # reads. Immutable task snapshots must still preserve their owners.
            barrier.wait(timeout=10)
            detail = toml.load(snapshot)["openaicompatible_detail"]
            relay = load_relay_options(sidecar)
            records[task_id] = {
                "snapshot": snapshot,
                "sidecar": sidecar,
                "input": Path(command[1]),
                "output": Path(command[command.index("--output") + 1]),
                "detail": detail,
                "relay": relay,
                "content": Path(command[1]).read_bytes(),
            }
            self.fake_outputs(command)

        def run(tenant):
            try:
                results[tenant] = self.translator.run_engine(
                    str(inputs[tenant]), configs[tenant], tenant
                )
            except Exception as exc:
                errors.append(exc)

        with mock.patch.object(next_engine, "execute_with_progress", execute):
            workers = [
                threading.Thread(target=run, args=(tenant,)) for tenant in ("a", "b")
            ]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=15)
                self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        for tenant in ("a", "b"):
            record = records[tenant]
            self.assertEqual(
                record["detail"]["openai_compatible_base_url"],
                f"https://{tenant}.example/v1",
            )
            self.assertEqual(
                record["detail"]["openai_compatible_api_key"], f"synthetic-{tenant}"
            )
            self.assertEqual(record["relay"]["headers"]["X-Tenant"], tenant)
            self.assertEqual(
                record["relay"]["api_format"],
                "responses" if tenant == "a" else "messages",
            )
            self.assertEqual(record["content"], inputs[tenant].read_bytes())
            self.assertEqual(
                Path(results[tenant][0]).read_bytes(), inputs[tenant].read_bytes()
            )
            self.assertEqual(get_filetype(results[tenant][0]), "mono")
            self.assertFalse(record["snapshot"].exists())
            self.assertFalse(record["sidecar"].exists())
        for key in ("snapshot", "sidecar", "input", "output"):
            self.assertNotEqual(records["a"][key], records["b"][key])
        self.assertNotEqual(results["a"][0], results["b"][0])
        self.assert_no_workspaces()

    def test_uploads_of_same_filename_do_not_overwrite_each_other(self):
        paths, workspaces = [], []
        try:
            for tenant in ("a", "b"):
                data = self.request(content=tenant.encode(), tenant=tenant)
                path, config = self.translator.process_request(data)
                paths.append(Path(path))
                workspaces.append(config.job_workspace)
            self.assertNotEqual(paths[0], paths[1])
            self.assertEqual([path.read_bytes() for path in paths], [b"a", b"b"])
        finally:
            for workspace in workspaces:
                workspace.cleanup()
        self.assert_no_workspaces()

    def test_sync_legacy_protocol_keeps_flat_download_names_and_existing_outputs(self):
        old = self.published / "paper.no_watermark.zh-CN.mono.pdf"
        old.write_bytes(b"previous-translation")
        with mock.patch.object(
            next_engine,
            "execute_with_progress",
            lambda cmd, *_, **_callbacks: self.fake_outputs(cmd),
        ):
            response = self.client.post("/translate", json=self.request())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "success")
        name = response.json["fileList"][0]
        self.assertEqual(name, os.path.basename(name))
        self.assertNotEqual(name, old.name)
        self.assertEqual(old.read_bytes(), b"previous-translation")
        download = self.client.get("/translatedFile/" + name)
        self.addCleanup(download.close)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, base64.b64decode(self.request()["fileContent"]))
        self.assertEqual(response.json["filePaths"], [str(self.published / name)])
        self.assert_no_workspaces()

    def test_async_protocol_finishes_with_downloadable_outputs_after_workspace_cleanup(
        self,
    ):
        data = self.request()
        data["asyncJob"] = True

        def execute(command, task_id, _options, _environment, on_progress=None):
            on_progress(
                {
                    "progress": 37,
                    "status": "running",
                    "message": "synthetic engine progress",
                }
            )
            self.assertEqual(self.translator.tasks.get_task(task_id)["progress"], 37)
            return self.fake_outputs(command)

        with mock.patch.object(next_engine, "execute_with_progress", execute):
            response = self.client.post("/translate", json=data)
            self.assertEqual(response.json["status"], "accepted")
            task_id = response.json["taskId"]
            deadline = time.monotonic() + 5
            task = None
            while time.monotonic() < deadline:
                task = self.translator.tasks.get_task(task_id)
                remaining = list((self.published / ".jobs").iterdir())
                if task and task.get("finished") and not remaining:
                    break
                time.sleep(0.01)
        self.assertIsNotNone(task)
        self.assertEqual(task["result"]["status"], "success", task)
        for name in task["result"]["fileList"]:
            download = self.client.get("/translatedFile/" + name)
            self.assertEqual(download.status_code, 200)
            download.close()
        self.assert_no_workspaces()

    def test_engine_failure_removes_temporary_configuration_and_upload(self):
        with mock.patch.object(
            next_engine,
            "execute_with_progress",
            side_effect=RuntimeError("synthetic failure"),
        ):
            response = self.client.post("/translate", json=self.request())
        self.assertEqual(response.status_code, 500)
        self.assert_no_workspaces()
        self.assertEqual(list(self.published.glob("*.pdf")), [])

    def test_invalid_terminal_operation_cleans_uploaded_workspace(self):
        response = self.client.post(
            "/crop-compare", json=self.request(name="already.crop-compare.pdf")
        )
        self.assertEqual(response.status_code, 409)
        self.assert_no_workspaces()

    def test_compare_existing_lr_dual_uses_isolated_upload_and_flat_publication(self):
        data = self.request(name="paper.LR_dual.pdf", content=b"synthetic-dual")
        response = self.client.post("/compare", json=data)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["status"], "success")
        self.assertTrue(response.json["fileList"][0].endswith(".compare.pdf"))
        self.assertEqual(
            Path(response.json["filePaths"][0]).read_bytes(), b"synthetic-dual"
        )
        self.assert_no_workspaces()

    def test_crop_publishes_valid_pdf_before_removing_uploaded_source(self):
        document = fitz.open()
        try:
            page = document.new_page()
            page.insert_text((72, 72), "Synthetic crop fixture")
            content = document.tobytes()
        finally:
            document.close()
        response = self.client.post("/crop", json=self.request(content=content))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["status"], "success")
        path = Path(response.json["filePaths"][0])
        with fitz.open(path) as cropped:
            self.assertGreater(len(cropped), 0)
            self.assertIn(
                "Synthetic crop fixture",
                "".join(page.get_text() for page in cropped),
            )
        self.assert_no_workspaces()

    def test_saved_glossary_survives_workspace_cleanup(self):
        data = self.request()
        data["saveGlossary"] = True

        def execute(command, *_, **_callbacks):
            output = Path(command[command.index("--output") + 1])
            (output / "paper.glossary.csv").write_text("source,target\nhello,你好\n")
            self.fake_outputs(command)

        with mock.patch.object(next_engine, "execute_with_progress", execute):
            response = self.client.post("/translate", json=data)
        self.assertEqual(response.json["status"], "success")
        self.assertTrue((self.published / "paper.glossary.csv").is_file())
        self.assertTrue(
            all(name.endswith(".pdf") for name in response.json["fileList"])
        )
        self.assert_no_workspaces()

    def test_credential_clear_cannot_interleave_persist_and_snapshot(self):
        written = threading.Event()
        allow_snapshot = threading.Event()
        clear_finished = threading.Event()
        snapshot = self.root / "snapshot.toml"
        config = Config(self.request())
        original = configuration_storage._update_config_file
        errors = []

        def update(current_config, path):
            original(current_config, path)
            written.set()
            if not allow_snapshot.wait(5):
                raise RuntimeError("snapshot barrier timeout")

        def save():
            try:
                update_config_file(config, str(self.saved), snapshot_file=str(snapshot))
            except Exception as exc:
                errors.append(exc)

        def clear():
            clear_saved_credential(str(self.saved), "openaicompatible")
            clear_finished.set()

        with mock.patch.object(configuration_storage, "_update_config_file", update):
            writer = threading.Thread(target=save)
            writer.start()
            self.assertTrue(written.wait(5))
            clearer = threading.Thread(target=clear)
            clearer.start()
            self.assertFalse(clear_finished.wait(0.05))
            allow_snapshot.set()
            writer.join(5)
            clearer.join(5)
        self.assertFalse(writer.is_alive())
        self.assertFalse(clearer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(
            toml.load(snapshot)["openaicompatible_detail"]["openai_compatible_api_key"],
            "synthetic-a",
        )
        self.assertEqual(
            toml.load(self.saved)["openaicompatible_detail"][
                "openai_compatible_api_key"
            ],
            "null",
        )

    def test_workspace_cleanup_rejects_a_target_outside_jobs(self):
        workspace = JobWorkspace(self.published)
        original_root = workspace.root
        workspace.root = self.root
        try:
            with self.assertRaises(ValueError):
                workspace.cleanup()
            self.assertTrue(self.saved.is_file())
        finally:
            workspace.root = original_root
            workspace.cleanup()

    def test_monitoring_resources_keep_their_urls_and_mime_types(self):
        for url, mime in (
            ("/", "text/html"),
            ("/assets/dashboard.js", "javascript"),
            ("/assets/dashboard.css", "text/css"),
            ("/favicon.svg", "image/svg+xml"),
            ("/bo.mp3", "audio/mpeg"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(mime, response.content_type)
                    self.assertGreater(len(response.data), 0)
                finally:
                    response.close()

    def test_lr_dual_converts_to_tb_and_preserves_crop_geometry(self):
        document = fitz.open()
        page = document.new_page(width=800, height=600)
        for x, text in (
            (50, "Translated left column"),
            (250, "Translated right column"),
            (450, "Original left column"),
            (650, "Original right column"),
        ):
            page.insert_text((x, 80), text)
        lr = self.root / "paper.LR_dual.pdf"
        document.save(lr)
        document.close()
        _, tb = self.translator.cropper.pdf_dual_mode(str(lr), "LR", "TB")
        with fitz.open(tb) as converted:
            self.assertEqual(len(converted), 2)
            self.assertEqual(converted[0].rect.width, 400)
        config = SimpleNamespace(pdf_w_offset=0, pdf_h_offset=0, pdf_offset_ratio=5.0)
        for kind, count, width in (("crop-compare", 2, 400), ("dual-cut", 4, 200)):
            with self.subTest(kind=kind):
                result = self.root / f"paper.{kind}.pdf"
                self.translator.cropper.crop_pdf(config, tb, "dual", str(result), kind)
                with fitz.open(result) as cropped:
                    self.assertEqual(len(cropped), count)
                    self.assertEqual(cropped[0].rect.width, width)


if __name__ == "__main__":
    unittest.main()
