"""Keep private Wenyi runtime data out of releases and source synchronization."""

from pdf2zh_server.paths import SERVER_ROOT

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(SERVER_ROOT))

import pdf2zh_server.source_update as auto_update

PRIVATE_DIRECTORIES = ("zotero-wenyi-venv", "wenyi-runtime", "wenyi-tasks")
REPOSITORY_ROOT = SERVER_ROOT.parent


class WenyiDistributionTests(unittest.TestCase):
    def test_release_package_contains_the_application_and_excludes_runtime_data(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "pdf2zh_pack_server_test", REPOSITORY_ROOT / "pack_server.py"
        )
        packager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packager)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "server"
            (source / "pdf2zh_server" / "web").mkdir(parents=True)
            for entry in (
                "server.py",
                "manage_packages.py",
                "update_packages.py",
                "requirements.txt",
                "notice.json",
                "config.yaml",
            ):
                (source / entry).write_text("# synthetic entry\n")
            (source / "pdf2zh_server" / "application.py").write_text("# application\n")
            (source / "pdf2zh_server" / "web" / "dashboard.js").write_text(
                "// dashboard\n"
            )
            (source / "tests").mkdir()
            (source / "tests" / "test_fixture.py").write_text("# test\n")
            (source / "config").mkdir()
            (source / "config" / "venv.json.example").write_text("{}")
            (source / "config" / "config.toml").write_text("credential = 'private'")
            for name in (*PRIVATE_DIRECTORIES, "translated", "server", "utils"):
                private = source / name
                private.mkdir()
                (private / "private-sentinel").write_text("must not be packaged")
            with patch.object(packager, "REPO", root):
                packager.build(root / "server.zip", include_tests=False)
                with zipfile.ZipFile(root / "server.zip") as archive:
                    names = archive.namelist()
                self.assertIn("server/server.py", names)
                self.assertIn("server/pdf2zh_server/application.py", names)
                self.assertIn("server/pdf2zh_server/web/dashboard.js", names)
                self.assertIn("server/config/venv.json.example", names)
                self.assertNotIn("server/tests/test_fixture.py", names)
                self.assertNotIn("server/config/config.toml", names)
                self.assertFalse(any("private-sentinel" in name for name in names))
                packager.build(root / "server.zip", include_tests=True)
                with zipfile.ZipFile(root / "server.zip") as archive:
                    self.assertIn("server/tests/test_fixture.py", archive.namelist())

    def test_source_update_preserves_wenyi_environment_sessions_and_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "server"
            target.mkdir()
            (target / "server.py").write_text('__version__ = "1.0.0"\n')
            (target / "utils").mkdir()
            (target / "utils" / "execute.py").write_text("# replaced legacy code")
            (target / "utils" / "custom_tool.py").write_text(
                "# keep unrelated local code"
            )
            (target / "config").mkdir()
            (target / "config" / "config.toml").write_text("custom_setting = 'keep'")
            for name in PRIVATE_DIRECTORIES:
                private = target / name
                private.mkdir()
                (private / "private-sentinel").write_text("original local data")
            release = root / "fixture.zip"
            with zipfile.ZipFile(release, "w") as archive:
                archive.writestr("server/server.py", '__version__ = "9.9.9"\n')
                archive.writestr(
                    "server/pdf2zh_server/application.py", "# new application"
                )
                for name in PRIVATE_DIRECTORIES:
                    archive.writestr(
                        f"server/{name}/private-sentinel", "must not overwrite"
                    )

            def download(_urls, destination, _label):
                shutil.copyfile(release, destination)

            with (
                patch("builtins.print"),
                patch.object(
                    auto_update, "get_xpi_info_from_repo", return_value=([], None)
                ),
                patch.object(auto_update, "_download_first", side_effect=download),
                self.assertRaises(SystemExit) as stopped,
            ):
                auto_update.perform_update_optimized(str(target), "1.0.0", "9.9.9")
            self.assertEqual(stopped.exception.code, 0)
            self.assertIn("9.9.9", (target / "server.py").read_text())
            self.assertTrue((target / "pdf2zh_server" / "application.py").is_file())
            self.assertFalse((target / "utils" / "execute.py").exists())
            self.assertTrue((target / "utils" / "custom_tool.py").is_file())
            self.assertEqual(
                (target / "config" / "config.toml").read_text(),
                "custom_setting = 'keep'",
            )
            for name in PRIVATE_DIRECTORIES:
                self.assertEqual(
                    (target / name / "private-sentinel").read_text(),
                    "original local data",
                )

    def test_release_source_order_and_notice_selection(self):
        github = auto_update._server_download_urls(
            "guaguastandup", "zotero-pdf2zh", "4.1.1", "github"
        )
        gitee = auto_update._server_download_urls(
            "guaguastandup", "zotero-pdf2zh", "4.1.1", "gitee"
        )
        self.assertNotEqual(github[0], gitee[0])
        self.assertTrue(
            any("/releases/download/v4.1.1/server.zip" in url for url in github)
        )
        self.assertTrue(all("repository/archive" not in url for url in github + gitee))
        first, second = auto_update._notice_urls("gitee")
        self.assertTrue(first.endswith("/raw/main/server/notice.json"))
        self.assertEqual(
            second,
            "https://raw.githubusercontent.com/guaguastandup/zotero-pdf2zh/main/server/notice.json",
        )
        notices = {
            "notices": [
                {"enabled": False, "title": "disabled"},
                {"affects": ["4.1.2"], "title": "current"},
                {"affects": ["4.1.0"], "title": "old"},
            ]
        }
        self.assertEqual(
            auto_update._select_notices(notices, "4.1.2"),
            [{"affects": ["4.1.2"], "title": "current"}],
        )
        self.assertFalse(
            auto_update._notice_applies(
                {"min_version": "4.1.0", "max_version": "4.1.1"}, "4.1.2"
            )
        )

    def test_source_update_rejects_wrong_version_before_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "server"
            target.mkdir()
            (target / "server.py").write_text('__version__ = "1.0.0"\n')
            release = root / "fixture.zip"
            with zipfile.ZipFile(release, "w") as archive:
                archive.writestr("server/server.py", '__version__ = "2.0.0"\n')
            with (
                patch("builtins.print"),
                patch.object(
                    auto_update, "get_xpi_info_from_repo", return_value=([], None)
                ),
                patch.object(
                    auto_update,
                    "_download_first",
                    side_effect=lambda urls, destination, label: shutil.copyfile(
                        release, destination
                    ),
                ),
                self.assertRaises(SystemExit) as stopped,
            ):
                auto_update.perform_update_optimized(str(target), "1.0.0", "9.9.9")
            self.assertEqual(stopped.exception.code, 1)
            self.assertIn("1.0.0", (target / "server.py").read_text())


if __name__ == "__main__":
    unittest.main()
