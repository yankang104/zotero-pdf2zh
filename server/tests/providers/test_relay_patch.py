import json
from pdf2zh_server.providers.relay_options import normalize_relay_options
from pdf2zh_server.providers.request_body import DEFAULT_MESSAGES_MAX_TOKENS
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import pdf2zh_server.providers.relay_patch as relay_patch
from pdf2zh_server.configuration.request import Config
from pdf2zh_server.engines.next_runtime.launcher import prepare_table_runtime_command
from pdf2zh_server.configuration.storage import update_config_file


class RelayOptionTests(unittest.TestCase):
    def test_plain_chat_needs_no_patch(self):
        extra = {"openai_compatible_timeout": "30", "zotero_api_format": "chat"}
        self.assertIsNone(normalize_relay_options(extra))
        self.assertEqual(extra, {"openai_compatible_timeout": "30"})
        self.assertIsNone(normalize_relay_options(None))

    def test_fields_are_removed_and_parsed(self):
        extra = {
            "zotero_api_format": "/v1/Responses",
            "zotero_extra_headers": '{"User-Agent": "codex_cli_rs/1.0", "X-Drop": null}',
            "zotero_extra_body": '{"stream": true, "store": false}',
            "openai_compatible_temperature": "0",
        }
        options = normalize_relay_options(extra)
        self.assertEqual(extra, {"openai_compatible_temperature": "0"})
        self.assertEqual(options["api_format"], "responses")
        self.assertEqual(
            options["headers"], {"User-Agent": "codex_cli_rs/1.0", "X-Drop": None}
        )
        self.assertEqual(options["extra_body"], {"stream": True, "store": False})

    def test_headers_only_still_patches_chat(self):
        options = normalize_relay_options({"zotero_extra_headers": {"X-App": "cli"}})
        self.assertEqual(options["api_format"], "chat")

    def test_invalid_values_are_rejected(self):
        for extra, pattern in (
            ({"zotero_api_format": "grpc"}, "接口类型"),
            ({"zotero_extra_headers": "{not json"}, "JSON"),
            ({"zotero_extra_headers": "[1]"}, "JSON 对象"),
            ({"zotero_extra_headers": '{"Bad Name": "x"}'}, "名称不合法"),
            ({"zotero_extra_headers": '{"X": "a\\nb"}'}, "换行"),
        ):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(ValueError, pattern):
                    normalize_relay_options(dict(extra))

    def test_summary_never_contains_values(self):
        options = normalize_relay_options(
            {
                "zotero_api_format": "messages",
                "zotero_extra_headers": '{"Authorization": "Bearer secret-token"}',
            }
        )
        self.assertNotIn("secret-token", relay_patch.describe_relay_options(options))

    def test_round_trip_through_file(self):
        options = normalize_relay_options(
            {
                "zotero_api_format": "messages",
                "zotero_extra_headers": '{"x-app": "cli", "x-api-key": null}',
            }
        )
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "relay.json")
            relay_patch.write_relay_options(path, options)
            self.assertEqual(relay_patch.load_relay_options(path), options)

    def test_bound_target_uses_a_hash_and_round_trips(self):
        options = normalize_relay_options({"zotero_api_format": "responses"})
        bound = relay_patch.bind_relay_target(
            options,
            base_url="https://r.example/v1/",
            model="m",
            api_key="credential-must-not-be-written",
            service="my-relay",
        )
        self.assertNotIn("target", options)
        self.assertEqual(bound["target"]["base_url"], "https://r.example/v1")
        self.assertNotIn("credential-must-not-be-written", json.dumps(bound))
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "relay.json")
            relay_patch.write_relay_options(path, bound)
            self.assertEqual(relay_patch.load_relay_options(path), bound)
        self.assertEqual(
            relay_patch._translator_identity(
                "https://r.example/v1/chat/completions/", "m", "k"
            ),
            relay_patch._translator_identity("https://r.example/v1", "m", "k"),
        )

    def test_cache_namespace_separates_endpoint_credentials_headers_and_body(self):
        options = normalize_relay_options(
            {
                "zotero_api_format": "chat",
                "zotero_extra_headers": {"X-Tenant": "tenant-secret"},
            }
        )
        identity = relay_patch._translator_identity(
            "https://a.example/v1", "m", "key-a"
        )
        first = relay_patch.relay_cache_namespace(options, identity)
        self.assertEqual(len(first), 64)
        self.assertNotIn("tenant-secret", first)
        variants = (
            relay_patch._translator_identity("https://b.example/v1", "m", "key-a"),
            relay_patch._translator_identity("https://a.example/v1", "m", "key-b"),
        )
        for variant in variants:
            self.assertNotEqual(
                first, relay_patch.relay_cache_namespace(options, variant)
            )
        self.assertEqual(
            first,
            relay_patch.relay_cache_namespace(
                {**options, "headers": {"x-tenant": "tenant-secret"}}, identity
            ),
        )
        for changed in (
            {**options, "headers": {"X-Tenant": "other"}},
            {**options, "extra_body": {"instructions": "other"}},
            {**options, "api_format": "responses"},
        ):
            self.assertNotEqual(
                first, relay_patch.relay_cache_namespace(changed, identity)
            )

    def test_unset_native_openai_base_uses_the_sdk_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            for base in (None, "", "null", "None"):
                self.assertEqual(
                    relay_patch._translator_identity(base, "m", "k")["base_url"],
                    "https://api.openai.com/v1",
                )
        with mock.patch.dict(
            os.environ, {"OPENAI_BASE_URL": "https://env.example/v1/"}
        ):
            self.assertEqual(
                relay_patch._translator_identity(None, "m", "k")["base_url"],
                "https://env.example/v1",
            )


class WireFormatTests(unittest.TestCase):
    def test_endpoint_urls(self):
        cases = (
            ("https://r.example/v1", "responses", "https://r.example/v1/responses"),
            ("https://r.example/v1/", "responses", "https://r.example/v1/responses"),
            (
                "https://r.example/v1/responses",
                "responses",
                "https://r.example/v1/responses",
            ),
            ("https://r.example/v1", "messages", "https://r.example/v1/messages"),
            ("https://r.example", "messages", "https://r.example/v1/messages"),
            ("https://r.example/api/", "messages", "https://r.example/api/v1/messages"),
            (
                "https://r.example/v1/messages",
                "messages",
                "https://r.example/v1/messages",
            ),
        )
        for base, api_format, expected in cases:
            with self.subTest(base=base, api_format=api_format):
                self.assertEqual(relay_patch.endpoint_url(base, api_format), expected)
        with self.assertRaises(ValueError):
            relay_patch.endpoint_url("", "responses")

    def test_headers_per_format_and_overrides(self):
        headers = relay_patch.build_headers("responses", "sk-1", {}, False)
        self.assertEqual(headers["Authorization"], "Bearer sk-1")
        self.assertNotIn("x-api-key", headers)

        headers = relay_patch.build_headers("messages", "sk-1", {}, True)
        self.assertEqual(headers["x-api-key"], "sk-1")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(headers["Accept"], "text/event-stream")

        headers = relay_patch.build_headers(
            "messages",
            "sk-1",
            {"X-API-KEY": None, "authorization": "Bearer sk-2", "User-Agent": "cli"},
            False,
        )
        self.assertNotIn("x-api-key", {name.lower() for name in headers})
        self.assertEqual(headers["authorization"], "Bearer sk-2")
        self.assertEqual(headers["User-Agent"], "cli")

    def test_bodies(self):
        messages = [{"role": "user", "content": "hi"}]
        body = relay_patch.build_body(
            "responses",
            "gpt-x",
            messages,
            {"temperature": 0.0, "reasoning_effort": "low"},
            {"store": False},
            json_mode=True,
        )
        self.assertEqual(
            body,
            {
                "model": "gpt-x",
                "input": messages,
                "temperature": 0.0,
                "reasoning": {"effort": "low"},
                "text": {"format": {"type": "json_object"}},
                "store": False,
            },
        )
        body = relay_patch.build_body(
            "messages",
            "claude-x",
            messages,
            {"reasoning_effort": "low"},
            {"max_tokens": 100},
        )
        self.assertEqual(
            body,
            {
                "model": "claude-x",
                "max_tokens": 100,
                "messages": messages,
                "output_config": {"effort": "low"},
            },
        )
        self.assertEqual(
            relay_patch.build_body(
                "chat",
                "model-x",
                messages,
                {"temperature": 0.7},
                {},
                template="minimal",
            ),
            {"model": "model-x", "messages": messages},
        )

    def test_json_responses(self):
        text, usage = relay_patch.parse_json_response(
            "responses",
            {
                "error": None,
                "status": "completed",
                "output": [
                    {"type": "reasoning", "summary": []},
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "你好"},
                        ],
                    },
                ],
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 2,
                    "total_tokens": 7,
                    "input_tokens_details": {"cached_tokens": 3},
                },
            },
        )
        self.assertEqual(text, "你好")
        self.assertEqual(usage, {"prompt": 5, "completion": 2, "total": 7, "cached": 3})
        text, usage = relay_patch.parse_json_response(
            "messages",
            {
                "type": "message",
                "stop_reason": "end_turn",
                "content": [
                    {"type": "thinking", "thinking": "x"},
                    {"type": "text", "text": "你好"},
                ],
                "usage": {
                    "input_tokens": 4,
                    "output_tokens": 1,
                    "cache_read_input_tokens": 2,
                },
            },
        )
        self.assertEqual(text, "你好")
        self.assertEqual(usage, {"prompt": 4, "completion": 1, "total": 5, "cached": 2})

    def test_json_errors(self):
        with self.assertRaisesRegex(relay_patch.RelayError, "bad key"):
            relay_patch.parse_json_response(
                "messages",
                {
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "bad key"},
                },
            )
        with self.assertRaises(relay_patch.RelayRateLimitError):
            relay_patch.parse_json_response(
                "messages",
                {
                    "type": "error",
                    "error": {"type": "overloaded_error", "message": "busy"},
                },
            )

    def test_usage_metadata_cannot_fail_a_completed_translation(self):
        text, usage = relay_patch.parse_json_response(
            "responses",
            {
                "status": "completed",
                "output_text": "done",
                "usage": {
                    "input_tokens": "5",
                    "output_tokens": "2",
                    "input_tokens_details": {"cached_tokens": {"invalid": 1}},
                },
            },
        )
        self.assertEqual(text, "done")
        self.assertEqual(usage, {"prompt": 5, "completion": 2, "total": 7, "cached": 0})

    def test_sse_streams(self):
        text, usage = relay_patch.parse_sse_lines(
            "chat",
            [
                'data: {"choices":[{"delta":{"content":"你"}}]}',
                "",
                'data: {"choices":[{"delta":{"content":"好"}}]}',
                "",
                'data: {"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":2,'
                '"total_tokens":6,"prompt_tokens_details":{"cached_tokens":1}}}',
                "",
                "data: [DONE]",
            ],
        )
        self.assertEqual(text, "你好")
        self.assertEqual(usage, {"prompt": 4, "completion": 2, "total": 6, "cached": 1})

        text, usage = relay_patch.parse_sse_lines(
            "responses",
            [
                "event: response.output_text.delta",
                'data: {"type":"response.output_text.delta","delta":"你"}',
                "",
                b'data: {"type":"response.output_text.delta","delta":"\xe5\xa5\xbd"}',
                "",
                'data: {"type":"response.completed","response":{"error":null,'
                '"status":"completed","usage":{"input_tokens":5,"output_tokens":2,"total_tokens":7}}}',
                "",
                "data: [DONE]",
            ],
        )
        self.assertEqual(text, "你好")
        self.assertEqual(usage["total"], 7)

        text, usage = relay_patch.parse_sse_lines(
            "messages",
            [
                'data: {"type":"message_start","message":{"usage":{"input_tokens":4,"output_tokens":0}}}',
                "",
                'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"x"}}',
                "",
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"你好"}}',
                "",
                'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":3}}',
                "",
                'data: {"type":"message_stop"}',
            ],
        )
        self.assertEqual(text, "你好")
        self.assertEqual(usage, {"prompt": 4, "completion": 3, "total": 7, "cached": 0})

        with self.assertRaisesRegex(relay_patch.RelayError, "nope"):
            relay_patch.parse_sse_lines(
                "responses",
                [
                    'data: {"type":"response.failed","response":{"error":{"message":"nope"}}}',
                ],
            )

    def test_sse_final_response_without_deltas(self):
        text, _ = relay_patch.parse_sse_lines(
            "responses",
            [
                'data: {"type":"response.completed","response":{"status":"completed","output":[{"type":"message",'
                '"content":[{"type":"output_text","text":"ok"}]}]}}',
            ],
        )
        self.assertEqual(text, "ok")

    def test_responses_json_requires_completed_status(self):
        for status in ("incomplete", "failed", "in_progress", None):
            with self.subTest(status=status):
                with self.assertRaises(relay_patch.RelayError):
                    relay_patch.parse_json_response(
                        "responses",
                        {
                            "status": status,
                            "output_text": "only-part",
                            "incomplete_details": {"reason": "max_output_tokens"},
                        },
                    )
        with self.assertRaisesRegex(relay_patch.RelayError, "max_output_tokens"):
            relay_patch.parse_json_response(
                "responses",
                {
                    "status": "incomplete",
                    "output_text": "only-part",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            )

    def test_messages_json_requires_a_normal_stop_reason(self):
        for reason in ("max_tokens", "tool_use", "pause_turn", "refusal", None):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(
                    relay_patch.RelayError, "stop_reason|max_tokens"
                ):
                    relay_patch.parse_json_response(
                        "messages",
                        {
                            "type": "message",
                            "stop_reason": reason,
                            "content": [{"type": "text", "text": "only-part"}],
                        },
                    )
        text, _ = relay_patch.parse_json_response(
            "messages",
            {
                "type": "message",
                "stop_reason": "stop_sequence",
                "content": [{"type": "text", "text": "complete"}],
            },
        )
        self.assertEqual(text, "complete")

    def test_truncated_or_incomplete_response_stream_is_rejected(self):
        delta = 'data: {"type":"response.output_text.delta","delta":"only-part"}'
        for tail in (
            [],
            ["data: [DONE]"],
            ['data: {"type":"response.incomplete","response":{"status":"incomplete"}}'],
            ['data: {"type":"response.completed","response":{"status":"incomplete"}}'],
            ['data: {"type":"response.completed","response":{}}'],
        ):
            with self.subTest(tail=tail):
                with self.assertRaises(relay_patch.RelayError):
                    relay_patch.parse_sse_lines("responses", [delta, "", *tail])

    def test_messages_stream_requires_stop_reason_and_message_stop(self):
        delta = 'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"only-part"}}'
        for tail in (
            [],
            ['data: {"type":"message_stop"}'],
            ['data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}'],
            [
                'data: {"type":"message_delta","delta":{"stop_reason":"max_tokens"}}',
                "",
                'data: {"type":"message_stop"}',
            ],
        ):
            with self.subTest(tail=tail):
                with self.assertRaises(relay_patch.RelayError):
                    relay_patch.parse_sse_lines("messages", [delta, "", *tail])

    def test_sse_multiline_records_event_names_and_final_authoritative_text(self):
        text, _ = relay_patch.parse_sse_lines(
            "responses",
            [
                ": keepalive",
                "event: response.output_text.delta",
                'data: {"delta":',
                'data: "missing-last-chunk"}',
                "",
                "event: response.completed",
                'data: {"response":{"status":"completed",',
                'data: "output_text":"complete-result"}}',
            ],
        )
        self.assertEqual(text, "complete-result")

    def test_invalid_json_event_is_not_silently_discarded(self):
        with self.assertRaisesRegex(relay_patch.RelayError, "JSON"):
            relay_patch.parse_sse_lines(
                "responses",
                [
                    'data: {"type":"response.output_text.delta","delta":"part"}',
                    "",
                    'data: {"type":"response.completed","response":',
                ],
            )

    def test_sse_utf8_bom_is_accepted(self):
        text, _ = relay_patch.parse_sse_lines(
            "responses",
            [
                '\ufeffdata: {"type":"response.output_text.delta","delta":"done"}',
                "",
                'data: {"type":"response.completed","response":{"status":"completed"}}',
            ],
        )
        self.assertEqual(text, "done")


class CommandWiringTests(unittest.TestCase):
    def test_flag_routes_through_runner_and_keeps_path(self):
        with tempfile.TemporaryDirectory() as folder:
            python = os.path.join(folder, "python.exe")
            open(python, "w").close()
            command = [
                python,
                "-m",
                "pdf2zh_next",
                "paper.pdf",
                "--openaicompatible",
                relay_patch.RELAY_PATCH_FLAG,
                "relay.json",
            ]
            wrapped = prepare_table_runtime_command(command)
        self.assertTrue(wrapped[2].endswith("runner.py"))
        self.assertEqual(
            wrapped[3:],
            [
                "none",
                relay_patch.RELAY_PATCH_FLAG,
                "relay.json",
                "paper.pdf",
                "--openaicompatible",
            ],
        )

    def test_missing_path_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare_table_runtime_command(
                ["python", "-m", "pdf2zh_next", relay_patch.RELAY_PATCH_FLAG]
            )


class CustomServiceConfigTests(unittest.TestCase):
    def _config(self, service, llm_api):
        with mock.patch("builtins.print"):
            return Config(
                {
                    "engine": "pdf2zh_next",
                    "next_service": service,
                    "llm_api": llm_api,
                }
            )

    def test_custom_name_maps_to_openai_compatible(self):
        config = self._config(
            "my-relay",
            {
                "service": "my-relay",
                "apiUrl": "https://r.example/v1",
                "apiKey": "sk",
                "model": "m",
            },
        )
        self.assertEqual(config.service, "openaicompatible")
        self.assertEqual(config.custom_service, "my-relay")

    def test_known_and_unconfigured_names_are_untouched(self):
        for service, llm_api in (
            ("deepseek", {"service": "deepseek", "apiUrl": "https://x"}),
            ("openailiked", {"service": "openailiked", "apiUrl": "https://x"}),
            ("bing", {}),
            ("my-relay", {}),
            ("my-relay", {"service": "other", "apiUrl": "https://x"}),
            ("my-relay", {"service": "my-relay", "apiUrl": ""}),
        ):
            with self.subTest(service=service, llm_api=llm_api):
                config = self._config(service, llm_api)
                self.assertEqual(config.service, service)
                self.assertIsNone(config.custom_service)

    def test_openai_service_also_accepts_relay_fields(self):
        import toml

        config = self._config(
            "openai",
            {
                "service": "openai",
                "apiUrl": "https://r.example/v1",
                "apiKey": "sk-test",
                "model": "m",
                "extraData": {"zotero_api_format": "responses"},
            },
        )
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.toml")
            open(path, "w", encoding="utf-8").close()
            with mock.patch("builtins.print"):
                update_config_file(config, path)
            saved = toml.load(path)["openai_detail"]
        self.assertEqual(config.relay_options["api_format"], "responses")
        self.assertFalse([key for key in saved if key.startswith("zotero_")])

    def test_relay_fields_stay_out_of_config_toml(self):
        import toml

        config = self._config(
            "my-relay",
            {
                "service": "my-relay",
                "apiUrl": "https://r.example/v1",
                "apiKey": "sk-test",
                "model": "m",
                "extraData": {
                    "zotero_api_format": "responses",
                    "zotero_extra_headers": '{"User-Agent": "ua"}',
                    "openai_compatible_timeout": "30",
                },
            },
        )
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.toml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("")
            with mock.patch("builtins.print"):
                update_config_file(config, path)
            saved = toml.load(path)["openaicompatible_detail"]
        self.assertEqual(config.relay_options["api_format"], "responses")
        self.assertEqual(config.relay_options["headers"], {"User-Agent": "ua"})
        self.assertEqual(saved["openai_compatible_base_url"], "https://r.example/v1")
        self.assertEqual(saved["openai_compatible_timeout"], "30")
        self.assertFalse([key for key in saved if key.startswith("zotero_")])


class _Headers(dict):
    """Header names are case-insensitive; HTTP clients differ in spelling."""

    def __init__(self, items):
        super().__init__((name.lower(), value) for name, value in items)

    def __getitem__(self, name):
        return super().__getitem__(name.lower())


class _FakeRelay(BaseHTTPRequestHandler):
    """Tiny local relay recording what the patched translator sends."""

    seen = []
    fail_first = 0
    response_override = None

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen.append((self.path, _Headers(self.headers.items()), body))
        if type(self).fail_first > 0:
            type(self).fail_first -= 1
            return self._send(429, "application/json", b'{"error":"slow down"}')
        if type(self).response_override is not None:
            return self._send(*type(self).response_override)
        if self.path.endswith("/chat/completions"):
            if body.get("stream"):
                events = (
                    'data: {"choices":[{"delta":{"content":"chat-"}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"stream"}}]}\n\n'
                    'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2,'
                    '"total_tokens":5}}\n\n'
                    "data: [DONE]\n\n"
                )
                return self._send(200, "text/event-stream", events.encode())
            payload = {
                "id": "c",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "chat-ok"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
            return self._send(200, "application/json", json.dumps(payload).encode())
        if self.path.endswith("/responses"):
            if body.get("stream"):
                events = (
                    'data: {"type":"response.output_text.delta","delta":"resp-"}\n\n'
                    'data: {"type":"response.output_text.delta","delta":"stream"}\n\n'
                    'data: {"type":"response.completed","response":{"status":"completed","usage":'
                    '{"input_tokens":3,"output_tokens":2,"total_tokens":5}}}\n\n'
                )
                return self._send(200, "text/event-stream", events.encode())
            payload = {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "resp-ok"}],
                    }
                ],
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            }
            return self._send(200, "application/json", json.dumps(payload).encode())
        if self.path.endswith("/messages"):
            payload = {
                "type": "message",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "<think>hidden</think>msg-ok"}],
                "usage": {"input_tokens": 4, "output_tokens": 1},
            }
            return self._send(200, "application/json", json.dumps(payload).encode())
        self._send(404, "application/json", b'{"error":"no route"}')

    def _send(self, status, content_type, data):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class RealUpstreamPatchTests(unittest.TestCase):
    """Runs the patch against the installed pdf2zh_next and a local fake relay."""

    @classmethod
    def setUpClass(cls):
        try:
            from pdf2zh_next.translator.translator_impl.openai import OpenAITranslator
            from pdf2zh_next.config.model import SettingsModel
            from pdf2zh_next.config.translate_engine_model import (
                OpenAICompatibleSettings,
            )
        except ImportError as exc:
            raise unittest.SkipTest(f"upstream test wheel missing: {exc}")
        cls.OpenAITranslator = OpenAITranslator
        cls.SettingsModel = SettingsModel
        cls.OpenAICompatibleSettings = OpenAICompatibleSettings
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeRelay)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.folder = tempfile.TemporaryDirectory()
        # A system proxy must not swallow requests to the local fake relay.
        cls.env = mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1,localhost"})
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.folder.cleanup()

    def setUp(self):
        _FakeRelay.seen = []
        _FakeRelay.fail_first = 0
        _FakeRelay.response_override = None

    def _translator(self, options, base_path="/v1", bind_target=True):
        if bind_target:
            options = relay_patch.bind_relay_target(
                options,
                base_url=self.base + base_path,
                model="model-x",
                api_key="sk-unit-test",
                service="unit-relay",
            )
        path = os.path.join(self.folder.name, "relay.json")
        relay_patch.write_relay_options(path, options)
        restore = relay_patch.install_relay_patch(path)
        self.relay_restore = restore
        self.addCleanup(restore)
        settings = self.SettingsModel(
            translate_engine_settings=self.OpenAICompatibleSettings(
                openai_compatible_model="model-x",
                openai_compatible_api_key="sk-unit-test",
                openai_compatible_base_url=self.base + base_path,
            ).transform()
        )
        settings.translation.lang_out = "zh-CN"
        settings.translation.ignore_cache = True
        self.main_settings = settings
        translator = self.OpenAITranslator(settings, None)
        self.addCleanup(translator.client.close)
        return translator

    def _native_translator(
        self, base_path="/terms/v1", model="term-x", api_key="term-key"
    ):
        settings = self.SettingsModel(
            translate_engine_settings=self.OpenAICompatibleSettings(
                openai_compatible_model=model,
                openai_compatible_api_key=api_key,
                openai_compatible_base_url=self.base + base_path,
            ).transform()
        )
        settings.translation.lang_out = "zh-CN"
        settings.translation.ignore_cache = True
        translator = self.OpenAITranslator(settings, None)
        self.addCleanup(translator.client.close)
        return translator

    @staticmethod
    def _options(**values):
        return normalize_relay_options(values)

    def test_chat_format_sends_custom_headers(self):
        translator = self._translator(
            self._options(
                zotero_extra_headers='{"User-Agent": "unit-agent/9", "X-App": "cli"}',
                zotero_extra_body='{"metadata": {"k": "v"}}',
            )
        )
        self.assertEqual(translator.do_translate("Hello"), "chat-ok")
        path, headers, body = _FakeRelay.seen[-1]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["User-Agent"], "unit-agent/9")
        self.assertEqual(headers["X-App"], "cli")
        self.assertEqual(body["metadata"], {"k": "v"})
        self.relay_restore()
        translator = self._translator(
            self._options(
                zotero_api_format="chat",
                zotero_auth_mode="x-api-key",
            )
        )
        self.assertFalse(hasattr(translator, "_zotero_relay"))
        self.assertEqual(translator.do_translate("Hello"), "chat-ok")
        _, headers, _ = _FakeRelay.seen[-1]
        self.assertEqual(headers["x-api-key"], "sk-unit-test")
        self.assertNotIn("authorization", headers)
        self.relay_restore()
        translator = self._translator(
            self._options(
                zotero_api_format="chat",
                zotero_body_template="minimal",
            )
        )
        translator.options["temperature"] = 0.7
        self.assertEqual(translator.do_translate("Hello"), "chat-ok")
        _, _, body = _FakeRelay.seen[-1]
        self.assertNotIn("temperature", body)

    def test_responses_format(self):
        translator = self._translator(
            self._options(
                zotero_api_format="responses",
                zotero_extra_headers='{"User-Agent": "codex-unit/1", "originator": "codex_cli_rs"}',
                zotero_extra_body='{"store": false, "instructions": "translate"}',
            )
        )
        self.assertEqual(translator.do_translate("Hello"), "resp-ok")
        path, headers, body = _FakeRelay.seen[-1]
        self.assertEqual(path, "/v1/responses")
        self.assertEqual(headers["User-Agent"], "codex-unit/1")
        self.assertEqual(headers["originator"], "codex_cli_rs")
        self.assertEqual(headers["Authorization"], "Bearer sk-unit-test")
        self.assertEqual(body["model"], "model-x")
        self.assertIs(body["store"], False)
        self.assertEqual(body["input"][0]["role"], "user")
        self.assertIn("Hello", body["input"][0]["content"])
        self.assertEqual(translator.token_count.value, 5)

    def test_responses_streaming(self):
        translator = self._translator(
            self._options(
                zotero_api_format="responses",
                zotero_extra_body='{"stream": true}',
            )
        )
        self.assertEqual(translator.do_llm_translate("raw prompt"), "resp-stream")
        _, headers, body = _FakeRelay.seen[-1]
        self.assertEqual(headers["Accept"], "text/event-stream")
        self.assertEqual(body["input"], [{"role": "user", "content": "raw prompt"}])
        self.assertIsNone(translator.do_llm_translate(None))
        self.relay_restore()
        translator = self._translator(
            self._options(
                zotero_api_format="chat",
                zotero_body_template="stream",
                zotero_auth_mode="x-api-key",
            )
        )
        self.assertEqual(translator.do_llm_translate("chat prompt"), "chat-stream")
        path, headers, body = _FakeRelay.seen[-1]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertIs(body["stream"], True)
        self.assertEqual(headers["x-api-key"], "sk-unit-test")
        self.assertNotIn("authorization", headers)
        self.assertEqual(translator.token_count.value, 5)

    def test_messages_format(self):
        translator = self._translator(
            self._options(
                zotero_api_format="messages",
                zotero_extra_headers='{"User-Agent": "claude-unit/1", "anthropic-beta": "b1"}',
            ),
            base_path="",
        )
        self.assertEqual(translator.do_translate("Hello"), "msg-ok")
        path, headers, body = _FakeRelay.seen[-1]
        self.assertEqual(path, "/v1/messages")
        self.assertEqual(headers["x-api-key"], "sk-unit-test")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(headers["anthropic-beta"], "b1")
        self.assertEqual(headers["User-Agent"], "claude-unit/1")
        self.assertEqual(body["max_tokens"], DEFAULT_MESSAGES_MAX_TOKENS)
        self.assertEqual(body["messages"][0]["role"], "user")

    def test_rate_limit_is_retried(self):
        translator = self._translator(self._options(zotero_api_format="responses"))
        _FakeRelay.fail_first = 1
        with mock.patch("tenacity.nap.time.sleep"):
            self.assertEqual(translator.do_translate("Hello"), "resp-ok")
        self.assertEqual(len(_FakeRelay.seen), 2)

    def test_http_error_is_reported(self):
        translator = self._translator(
            self._options(zotero_api_format="responses"), base_path="/nowhere/v9x"
        )
        translator._zotero_relay["url"] = self.base + "/missing"
        with self.assertRaisesRegex(relay_patch.RelayError, "HTTP 404"):
            translator.do_translate("Hello")

    def test_independent_term_translators_keep_their_own_transport(self):
        main = self._translator(
            self._options(
                zotero_api_format="responses",
                zotero_extra_headers='{"X-App": "main-only"}',
                zotero_extra_body='{"instructions": "main-only"}',
            )
        )
        for base_path, model, key in (
            ("/terms/v1", "model-x", "sk-unit-test"),
            ("/v1", "term-model", "sk-unit-test"),
            ("/v1", "model-x", "other-credential"),
            ("/v1", "model-x", "sk-unit-test"),
        ):
            with self.subTest(base_path=base_path, model=model, key=key):
                term = self._native_translator(base_path, model, key)
                self.assertFalse(hasattr(term, "_zotero_relay"))
                self.assertEqual(term.do_llm_translate("term prompt"), "chat-ok")
                path, headers, body = _FakeRelay.seen[-1]
                self.assertEqual(path, base_path + "/chat/completions")
                self.assertNotIn("x-app", headers)
                self.assertNotIn("instructions", body)
                self.assertNotIn("zotero_relay_namespace", term.cache.params)
        self.assertEqual(main.do_translate("main"), "resp-ok")
        self.assertEqual(_FakeRelay.seen[-1][0], "/v1/responses")

    def test_translators_sharing_the_main_settings_keep_relay_options(self):
        main = self._translator(self._options(zotero_api_format="responses"))
        shared = self.OpenAITranslator(self.main_settings.model_copy(), None)
        self.addCleanup(shared.client.close)
        self.assertTrue(hasattr(shared, "_zotero_relay"))
        self.assertEqual(shared.do_llm_translate("shared"), "resp-ok")
        self.assertEqual(
            main.cache.params["zotero_relay_namespace"],
            shared.cache.params["zotero_relay_namespace"],
        )

    def test_mismatched_main_target_fails_before_any_http_request(self):
        path = os.path.join(self.folder.name, "mismatch.json")
        options = relay_patch.bind_relay_target(
            self._options(zotero_api_format="responses"),
            base_url=self.base + "/v1",
            model="expected-model",
            api_key="expected-key",
            service="main",
        )
        relay_patch.write_relay_options(path, options)
        restore = relay_patch.install_relay_patch(path)
        self.addCleanup(restore)
        with self.assertRaisesRegex(RuntimeError, "没有发起 API 请求"):
            self._native_translator("/v1", "unexpected-model", "expected-key")
        self.assertEqual(_FakeRelay.seen, [])

    def test_legacy_sidecar_binds_the_first_translator_only(self):
        main = self._translator(
            self._options(zotero_api_format="messages"), bind_target=False
        )
        term = self._native_translator()
        self.assertTrue(hasattr(main, "_zotero_relay"))
        self.assertFalse(hasattr(term, "_zotero_relay"))
        self.assertEqual(term.do_translate("term"), "chat-ok")

    def test_restore_closes_owned_http_clients_and_preserves_sdk_client(self):
        translator = self._translator(self._options(zotero_api_format="responses"))
        owned = translator._zotero_relay["client"]
        self.assertFalse(owned.is_closed)
        self.assertFalse(translator.client.is_closed())
        self.relay_restore()
        self.relay_restore()
        self.assertTrue(owned.is_closed)
        self.assertFalse(translator.client.is_closed())
        self.assertEqual(translator.do_translate("after restore"), "chat-ok")

    def test_chat_restore_does_not_close_the_shared_sdk_transport(self):
        translator = self._translator(
            self._options(
                zotero_extra_headers='{"X-App": "chat"}',
            )
        )
        self.relay_restore()
        self.assertFalse(translator.client.is_closed())
        self.assertEqual(translator.do_translate("after restore"), "chat-ok")

    def test_real_http_incomplete_and_truncated_outputs_raise(self):
        cases = (
            (
                "responses",
                "application/json",
                {
                    "status": "incomplete",
                    "output_text": "part",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            ),
            (
                "responses",
                "text/event-stream",
                'data: {"type":"response.output_text.delta","delta":"part"}\n\n',
            ),
            (
                "messages",
                "application/json",
                {
                    "type": "message",
                    "stop_reason": "max_tokens",
                    "content": [{"type": "text", "text": "part"}],
                },
            ),
            (
                "messages",
                "application/json",
                {
                    "type": "message",
                    "stop_reason": "end_turn",
                    "content": [
                        {"type": "text", "text": "<think>only reasoning</think>"}
                    ],
                },
            ),
            (
                "messages",
                "text/event-stream",
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"part"}}\n\n'
                'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n\n',
            ),
        )
        for api_format, content_type, payload in cases:
            with self.subTest(api_format=api_format, content_type=content_type):
                translator = self._translator(
                    self._options(zotero_api_format=api_format)
                )
                data = json.dumps(payload) if isinstance(payload, dict) else payload
                _FakeRelay.response_override = (200, content_type, data.encode())
                with self.assertRaises(relay_patch.RelayError):
                    translator.do_llm_translate("input")
                self.relay_restore()

    def test_real_http_multiline_stream_completes(self):
        translator = self._translator(
            self._options(
                zotero_api_format="messages",
                zotero_extra_body='{"stream": true}',
            )
        )
        data = (
            "event: content_block_delta\n"
            'data: {"delta":{"type":"text_delta",\n'
            'data: "text":"complete"}}\n\n'
            'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n\n'
            'data: {"type":"message_stop"}\n\n'
        )
        _FakeRelay.response_override = (200, "text/event-stream", data.encode())
        self.assertEqual(translator.do_llm_translate("input"), "complete")

    def test_cache_namespace_has_no_sensitive_headers(self):
        translator = self._translator(
            self._options(
                zotero_api_format="responses",
                zotero_extra_headers='{"Authorization":"Bearer credential-secret"}',
                zotero_extra_body='{"metadata":{"token":"body-secret"}}',
            )
        )
        saved = json.dumps(translator.cache.params)
        self.assertIn("zotero_relay_namespace", saved)
        self.assertNotIn("credential-secret", saved)
        self.assertNotIn("body-secret", saved)

    def test_real_cache_hits_stay_with_the_same_endpoint_and_headers(self):
        from pdf2zh_next.translator import cache

        database = cache.SqliteDatabase(
            os.path.join(self.folder.name, "relay-cache.db")
        )
        with database.bind_ctx(
            [cache._TranslationCache], bind_refs=False, bind_backrefs=False
        ):
            database.create_tables([cache._TranslationCache], safe=True)
            try:
                for index, (base_path, tenant) in enumerate(
                    (
                        ("/v1", "tenant-a"),
                        ("/v1", "tenant-b"),
                        ("/other/v1", "tenant-a"),
                    )
                ):
                    with self.subTest(base_path=base_path, tenant=tenant):
                        translator = self._translator(
                            self._options(
                                zotero_api_format="responses",
                                zotero_extra_headers=json.dumps({"X-Tenant": tenant}),
                            ),
                            base_path=base_path,
                        )
                        translator.ignore_cache = False
                        translator.rate_limiter = mock.Mock()
                        expected = f"provider-{index}"
                        payload = json.dumps(
                            {
                                "status": "completed",
                                "output_text": expected,
                            }
                        ).encode()
                        _FakeRelay.response_override = (
                            200,
                            "application/json",
                            payload,
                        )
                        seen_before = len(_FakeRelay.seen)
                        self.assertEqual(translator.translate("same input"), expected)
                        self.assertEqual(len(_FakeRelay.seen), seen_before + 1)
                        self.assertEqual(translator.translate("same input"), expected)
                        self.assertEqual(len(_FakeRelay.seen), seen_before + 1)
                        self.relay_restore()
            finally:
                database.close()

    def test_restore_returns_original_methods(self):
        before = dict(self.OpenAITranslator.__dict__)
        path = os.path.join(self.folder.name, "restore.json")
        relay_patch.write_relay_options(
            path, self._options(zotero_api_format="messages")
        )
        restore = relay_patch.install_relay_patch(path)
        self.assertIsNot(self.OpenAITranslator.do_translate, before["do_translate"])
        with self.assertRaisesRegex(RuntimeError, "重复安装"):
            relay_patch.install_relay_patch(path)
        restore()
        for name in ("__init__", "do_translate", "do_llm_translate"):
            self.assertIs(self.OpenAITranslator.__dict__[name], before[name])


if __name__ == "__main__":
    unittest.main()
