"""Build Chat, Responses and Messages request bodies from translator options."""

from __future__ import annotations

import json
from copy import deepcopy

BODY_FIELD = "zotero_extra_body"
BODY_TEMPLATE_FIELD = "zotero_body_template"
BODY_TEMPLATES = ("standard", "minimal", "stream")
DEFAULT_MESSAGES_MAX_TOKENS = 8192

_NESTED_BODY_FIELDS = {
    "reasoning",
    "text",
    "response_format",
    "output_config",
    "stream_options",
    "prompt_cache_options",
}
_TRANSPORT_OPTIONS = {"extra_body", "extra_headers", "extra_query", "timeout"}


def parse_extra_body(value) -> dict:
    """Parse the editor's extra body using the existing relay JSON behavior."""
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            value = json.loads(text)
        except ValueError as exc:
            raise ValueError(
                f"{BODY_FIELD} 不是合法的 JSON: {exc}。"
                '正确写法示例: {"User-Agent": "my-client/1.0"}'
            ) from exc
    if not isinstance(value, dict):
        raise ValueError(f'{BODY_FIELD} 必须是 JSON 对象，例如 {{"名称": "值"}}。')
    return value


def _merge_object(target, fields):
    for name, value in fields.items():
        if isinstance(value, dict) and isinstance(target.get(name), dict):
            _merge_object(target[name], value)
        else:
            target[name] = deepcopy(value)


def _merge_body_fields(body, fields):
    for name, value in fields.items():
        if (
            name in _NESTED_BODY_FIELDS
            and isinstance(value, dict)
            and isinstance(body.get(name), dict)
        ):
            _merge_object(body[name], value)
        else:
            body[name] = deepcopy(value)


def _messages_body(model, messages):
    system_blocks = []
    conversation = []
    for message in messages:
        if message["role"] in ("system", "developer"):
            content = message["content"]
            system_blocks.extend(
                [{"type": "text", "text": content}]
                if isinstance(content, str)
                else deepcopy(content)
            )
        else:
            conversation.append(deepcopy(message))
    body = {
        "model": model,
        "messages": conversation,
        "max_tokens": DEFAULT_MESSAGES_MAX_TOKENS,
    }
    if system_blocks:
        body["system"] = system_blocks
    return body


def build_request_body(
    api_format,
    model,
    messages,
    options,
    extra_body,
    *,
    template="standard",
    api_version="2023-06-01",
    json_mode=False,
):
    """Return JSON fields; options already reflect the translator's send switches.

    Minimal skips optional engine fields. Explicit extra_body fields still apply,
    first from engine options and then from the relay editor. Known nested objects
    merge so an extra reasoning summary retains the configured effort.
    """
    options = options or {}
    include_engine_fields = template != "minimal"

    if api_format == "chat":
        body = {"model": model, "messages": deepcopy(messages)}
        if include_engine_fields:
            body.update(
                (name, deepcopy(value))
                for name, value in options.items()
                if name not in _TRANSPORT_OPTIONS
            )
            if json_mode:
                body["response_format"] = {"type": "json_object"}
    elif api_format == "responses":
        body = {"model": model, "input": deepcopy(messages)}
        if include_engine_fields:
            if "temperature" in options:
                body["temperature"] = options["temperature"]
            if options.get("reasoning_effort"):
                body["reasoning"] = {"effort": options["reasoning_effort"]}
            if json_mode:
                body["text"] = {"format": {"type": "json_object"}}
    elif api_format == "messages":
        body = _messages_body(model, messages)
        if include_engine_fields:
            if "temperature" in options and api_version == "2023-06-01":
                body["temperature"] = options["temperature"]
            if options.get("reasoning_effort"):
                body["output_config"] = {"effort": options["reasoning_effort"]}
    else:
        raise ValueError(f"Unsupported relay format: {api_format}")

    if template == "stream":
        body["stream"] = True
    _merge_body_fields(body, options.get("extra_body") or {})
    _merge_body_fields(body, extra_body or {})
    return body
