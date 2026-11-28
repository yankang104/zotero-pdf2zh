"""Clear saved credential tests: plugin deletion must wipe the server-side key."""

import os
import tempfile
import unittest

import toml

from pdf2zh_server.configuration.storage import clear_saved_credential


class ClearSavedCredentialTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def write_toml(self, data):
        path = os.path.join(self.tmpdir, "config.toml")
        with open(path, "w", encoding="utf-8") as f:
            toml.dump(data, f)
        return path

    def test_clears_deepseek_key_in_toml(self):
        path = self.write_toml(
            {
                "deepseek_detail": {
                    "deepseek_api_key": "sk-live-1234",
                    "deepseek_model": "deepseek-chat",
                },
                "translation": {"lang_out": "zh-CN"},
            }
        )

        self.assertTrue(clear_saved_credential(path, "deepseek"))

        with open(path, "r", encoding="utf-8") as f:
            data = toml.load(f)
        self.assertEqual(data["deepseek_detail"]["deepseek_api_key"], "null")
        self.assertEqual(data["deepseek_detail"]["deepseek_model"], "deepseek-chat")
        self.assertEqual(data["translation"]["lang_out"], "zh-CN")

    def test_placeholder_key_is_noop(self):
        path = self.write_toml({"deepseek_detail": {"deepseek_api_key": "null"}})

        self.assertFalse(clear_saved_credential(path, "deepseek"))

        with open(path, "r", encoding="utf-8") as f:
            data = toml.load(f)
        self.assertEqual(data["deepseek_detail"]["deepseek_api_key"], "null")

    def test_missing_service_section_is_noop(self):
        path = self.write_toml({"openai_detail": {"openai_api_key": "sk-openai"}})

        self.assertFalse(clear_saved_credential(path, "deepseek"))

        with open(path, "r", encoding="utf-8") as f:
            data = toml.load(f)
        self.assertEqual(data["openai_detail"]["openai_api_key"], "sk-openai")

    def test_resolves_service_alias(self):
        path = self.write_toml(
            {"siliconflow_detail": {"siliconflow_api_key": "sk-silicon"}}
        )

        self.assertTrue(clear_saved_credential(path, "silicon"))

        with open(path, "r", encoding="utf-8") as f:
            data = toml.load(f)
        self.assertEqual(data["siliconflow_detail"]["siliconflow_api_key"], "null")

    def test_service_without_api_key_mapping_is_noop(self):
        path = self.write_toml({"bing_detail": {"bing_host": "x"}})

        self.assertFalse(clear_saved_credential(path, "bing"))

    def test_missing_file_is_noop(self):
        self.assertFalse(
            clear_saved_credential(
                os.path.join(self.tmpdir, "nope.toml"), "deepseek"
            )
        )


if __name__ == "__main__":
    unittest.main()
