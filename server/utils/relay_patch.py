"""Custom relay support for the pdf2zh_next OpenAI-compatible translator.

Adds three things upstream pdf2zh_next does not offer:

* custom HTTP request headers (for relays that check the client identity),
* extra JSON body fields,
* two more wire formats besides Chat Completions: OpenAI ``/v1/responses``
  and Anthropic ``/v1/messages``.

Like the DeepSeek flash hook, this patches the translator class in memory in
the engine process only. Installed package files are never modified, and the
patch is undone when the job ends.

The first half of this file is plain Python used by the Server process. The
second half (``install_relay_patch``) runs inside the engine process.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

RELAY_PATCH_FLAG = "--zotero-relay-patch"

FORMAT_FIELD = "zotero_api_format"
HEADERS_FIELD = "zotero_extra_headers"
BODY_FIELD = "zotero_extra_body"
RELAY_FIELDS = (FORMAT_FIELD, HEADERS_FIELD, BODY_FIELD)

FORMAT_CHAT = "chat"
FORMAT_RESPONSES = "responses"
FORMAT_MESSAGES = "messages"
API_FORMATS = (FORMAT_CHAT, FORMAT_RESPONSES, FORMAT_MESSAGES)

_FORMAT_ALIASES = {
    "": FORMAT_CHAT,
    "chat": FORMAT_CHAT,
    "chat/completions": FORMAT_CHAT,
    "chat_completions": FORMAT_CHAT,
    "completions": FORMAT_CHAT,
    "openai": FORMAT_CHAT,
    "responses": FORMAT_RESPONSES,
    "response": FORMAT_RESPONSES,
    "codex": FORMAT_RESPONSES,
    "messages": FORMAT_MESSAGES,
    "message": FORMAT_MESSAGES,
    "anthropic": FORMAT_MESSAGES,
    "claude": FORMAT_MESSAGES,
}

DEFAULT_MESSAGES_MAX_TOKENS = 8192
DEFAULT_TIMEOUT_SECONDS = 600.0
ANTHROPIC_VERSION = "2023-06-01"

_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_VERSION_SUFFIX = re.compile(r"/v\d+[a-z0-9]*$", re.IGNORECASE)


# --------------------------------------------------------------------------
# Option parsing (Server process and engine process)
# --------------------------------------------------------------------------

def parse_api_format(value) -> str:
    text = str(value or "").strip().lower().strip("/")
    if text.startswith("v1/"):
        text = text[3:]
    if text not in _FORMAT_ALIASES:
        raise ValueError(
            f"接口类型 {FORMAT_FIELD} 只能是 chat / responses / messages，"
            f"收到的是: {value!r}"
        )
    return _FORMAT_ALIASES[text]


def _parse_json_object(value, field: str) -> dict:
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
                f"{field} 不是合法的 JSON: {exc}。"
                '正确写法示例: {"User-Agent": "my-client/1.0"}'
            ) from exc
    if not isinstance(value, dict):
        raise ValueError(f'{field} 必须是 JSON 对象，例如 {{"名称": "值"}}。')
    return value


def parse_extra_headers(value) -> dict:
    """Return {name: str | None}. ``None`` means "do not send this header"."""
    headers = {}
    for name, raw in _parse_json_object(value, HEADERS_FIELD).items():
        name = str(name).strip()
        if not _HEADER_NAME.match(name):
            raise ValueError(f"{HEADERS_FIELD} 里的请求头名称不合法: {name!r}")
        if raw is None:
            headers[name] = None
            continue
        if isinstance(raw, bool):
            raw = "true" if raw else "false"
        if not isinstance(raw, (str, int, float)):
            raise ValueError(
                f"{HEADERS_FIELD} 里 {name} 的值必须是字符串、数字或 null。"
            )
        text = str(raw)
        if "\r" in text or "\n" in text:
            raise ValueError(f"{HEADERS_FIELD} 里 {name} 的值不能包含换行。")
        headers[name] = text
    return headers


def normalize_relay_options(extra_data):
    """Pop the relay fields out of plugin extraData and validate them.

    Returns ``None`` when nothing relay-specific was requested, so ordinary
    OpenAI-compatible jobs keep using the untouched upstream code path.
    """
    if not isinstance(extra_data, dict):
        return None
    raw_format = extra_data.pop(FORMAT_FIELD, None)
    raw_headers = extra_data.pop(HEADERS_FIELD, None)
    raw_body = extra_data.pop(BODY_FIELD, None)

    api_format = parse_api_format(raw_format)
    headers = parse_extra_headers(raw_headers)
    body = _parse_json_object(raw_body, BODY_FIELD)

    if api_format == FORMAT_CHAT and body.get("stream"):
        raise ValueError(
            f"chat 接口类型不支持在 {BODY_FIELD} 里设置 stream=true；"
            "需要流式请求时请改用 responses 或 messages 接口类型。"
        )
    if api_format == FORMAT_CHAT and not headers and not body:
        return None
    return {"api_format": api_format, "headers": headers, "extra_body": body}


def write_relay_options(path, options) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(options, handle, ensure_ascii=False)


def load_relay_options(path) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return {
        "api_format": parse_api_format(data.get("api_format")),
        "headers": parse_extra_headers(data.get("headers")),
        "extra_body": _parse_json_object(data.get("extra_body"), BODY_FIELD),
    }


def describe_relay_options(options) -> str:
    """Log-safe summary: header and body *names* only, never their values."""
    return (
        f"format={options['api_format']}, "
        f"headers={sorted(options['headers'])}, "
        f"extra_body_keys={sorted(options['extra_body'])}"
    )


# --------------------------------------------------------------------------
# Wire format helpers (pure functions, no network)
# --------------------------------------------------------------------------

def endpoint_url(base_url, api_format: str) -> str:
    """Build the request URL from the Base URL the user typed.

    * A Base URL that already ends in the endpoint is used unchanged.
    * responses: ``<base>/responses`` (same rule as the OpenAI SDK).
    * messages: ``<base>/messages`` when the base ends in ``/v1``,
      otherwise ``<base>/v1/messages`` (same rule as the Anthropic SDK).
    """
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("使用自定义接口类型时必须填写 Base URL。")
    if api_format == FORMAT_RESPONSES:
        return base if base.endswith("/responses") else base + "/responses"
    if api_format == FORMAT_MESSAGES:
        if base.endswith("/messages"):
            return base
        if _VERSION_SUFFIX.search(base):
            return base + "/messages"
        return base + "/v1/messages"
    raise ValueError(f"Unsupported relay format: {api_format}")


def build_headers(api_format: str, api_key, custom: dict, stream: bool) -> dict:
    headers = {
        "content-type": ("Content-Type", "application/json"),
        "accept": ("Accept", "text/event-stream" if stream else "application/json"),
    }
    if api_format == FORMAT_MESSAGES:
        headers["x-api-key"] = ("x-api-key", str(api_key or ""))
        headers["anthropic-version"] = ("anthropic-version", ANTHROPIC_VERSION)
    else:
        headers["authorization"] = ("Authorization", f"Bearer {api_key or ''}")
    # User headers win; header names are case-insensitive. null removes one.
    for name, value in (custom or {}).items():
        if value is None:
            headers.pop(name.lower(), None)
        else:
            headers[name.lower()] = (name, value)
    return dict(headers.values())


def build_body(api_format, model, messages, options, extra_body, json_mode=False):
    """Translate upstream Chat Completions options into the target format."""
    options = options or {}
    if api_format == FORMAT_RESPONSES:
        body = {"model": model, "input": messages}
        if "temperature" in options:
            body["temperature"] = options["temperature"]
        if options.get("reasoning_effort"):
            body["reasoning"] = {"effort": options["reasoning_effort"]}
        if json_mode:
            body["text"] = {"format": {"type": "json_object"}}
    elif api_format == FORMAT_MESSAGES:
        body = {
            "model": model,
            "max_tokens": DEFAULT_MESSAGES_MAX_TOKENS,
            "messages": messages,
        }
        if "temperature" in options:
            body["temperature"] = options["temperature"]
    else:
        raise ValueError(f"Unsupported relay format: {api_format}")
    if isinstance(options.get("extra_body"), dict):
        body.update(options["extra_body"])
    body.update(extra_body or {})
    return body


class RelayError(RuntimeError):
    """The relay answered, but not with a usable translation."""


class RelayRateLimitError(RelayError):
    """HTTP 429/529 or an overloaded error: retried like upstream does."""


def _error_message(error) -> str:
    if isinstance(error, dict):
        kind = error.get("type") or error.get("code") or ""
        message = error.get("message") or json.dumps(error, ensure_ascii=False)
        return f"{kind}: {message}" if kind else str(message)
    return str(error)


def _raise_api_error(error):
    message = _error_message(error)
    kind = str(error.get("type") or error.get("code") or "") if isinstance(error, dict) else ""
    if "overloaded" in kind or "rate_limit" in kind:
        raise RelayRateLimitError(message)
    raise RelayError(f"中转站返回错误: {message}")


def _responses_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"]:
        return data["output_text"]
    parts = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for block in item.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "output_text":
                parts.append(str(block.get("text") or ""))
    return "".join(parts)


def _messages_text(data: dict) -> str:
    return "".join(
        str(block.get("text") or "")
        for block in data.get("content") or []
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _usage(api_format: str, usage) -> dict:
    """Normalize token usage to {prompt, completion, total, cached}."""
    if not isinstance(usage, dict):
        return {}
    prompt = usage.get("input_tokens") or 0
    completion = usage.get("output_tokens") or 0
    if api_format == FORMAT_RESPONSES:
        details = usage.get("input_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else 0
    else:
        cached = usage.get("cache_read_input_tokens")
    return {
        "prompt": int(prompt),
        "completion": int(completion),
        "total": int(usage.get("total_tokens") or (prompt + completion)),
        "cached": int(cached or 0),
    }


def parse_json_response(api_format: str, data):
    """Return (text, usage) from a non-streaming response body."""
    if not isinstance(data, dict):
        raise RelayError("中转站返回的不是 JSON 对象。")
    if data.get("error") or data.get("type") == "error":
        _raise_api_error(data.get("error") or data)
    if api_format == FORMAT_RESPONSES:
        text = _responses_text(data)
    else:
        text = _messages_text(data)
    return text, _usage(api_format, data.get("usage"))


def parse_sse_lines(api_format: str, lines):
    """Return (text, usage) from Server-Sent-Events lines."""
    parts = []
    usage = {}
    final = None
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type") or ""
        if kind == "error" or event.get("error"):
            _raise_api_error(event.get("error") or event)
        if api_format == FORMAT_RESPONSES:
            if kind == "response.output_text.delta":
                parts.append(str(event.get("delta") or ""))
            elif kind in ("response.completed", "response.incomplete"):
                final = event.get("response") if isinstance(event.get("response"), dict) else None
                if final:
                    usage = _usage(api_format, final.get("usage"))
            elif kind == "response.failed":
                response = event.get("response") or {}
                _raise_api_error(response.get("error") or "response.failed")
        else:
            if kind == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta":
                    parts.append(str(delta.get("text") or ""))
            elif kind == "message_start":
                message = event.get("message") or {}
                usage = _usage(api_format, message.get("usage"))
            elif kind == "message_delta":
                extra = _usage(api_format, event.get("usage"))
                if extra:
                    prompt = extra["prompt"] or usage.get("prompt", 0)
                    usage = {
                        "prompt": prompt,
                        "completion": extra["completion"],
                        "total": prompt + extra["completion"],
                        "cached": extra["cached"] or usage.get("cached", 0),
                    }
    text = "".join(parts)
    if not text and final:
        text = _responses_text(final)
    return text, usage


def looks_like_sse(content_type, text) -> bool:
    if "text/event-stream" in str(content_type or "").lower():
        return True
    head = str(text or "").lstrip()[:16]
    return head.startswith("event:") or head.startswith("data:")


# --------------------------------------------------------------------------
# Engine-process patch
# --------------------------------------------------------------------------

def _post(translator, messages, json_mode):
    """One HTTP round trip. Returns (text, usage)."""
    state = translator._zotero_relay
    api_format = state["api_format"]
    body = build_body(
        api_format,
        translator.model,
        messages,
        translator.options,
        state["extra_body"],
        json_mode=json_mode,
    )
    stream = bool(body.get("stream"))
    headers = build_headers(api_format, state["api_key"], state["headers"], stream)
    client = state["client"]

    if stream:
        with client.stream("POST", state["url"], headers=headers, json=body) as response:
            if response.status_code >= 400:
                response.read()
                _raise_http_error(response.status_code, response.text)
            return parse_sse_lines(api_format, response.iter_lines())

    response = client.post(state["url"], headers=headers, json=body)
    if response.status_code >= 400:
        _raise_http_error(response.status_code, response.text)
    # Some relays always answer with an event stream, whatever was asked.
    if looks_like_sse(response.headers.get("content-type"), response.text):
        return parse_sse_lines(api_format, response.text.splitlines())
    try:
        data = response.json()
    except ValueError as exc:
        raise RelayError(
            "中转站返回的内容不是 JSON: " + response.text[:300]
        ) from exc
    return parse_json_response(api_format, data)


def _raise_http_error(status: int, text: str):
    snippet = str(text or "").strip()[:500]
    if status in (429, 529):
        raise RelayRateLimitError(f"HTTP {status}: {snippet}")
    raise RelayError(f"中转站返回 HTTP {status}: {snippet}")


def _count_usage(translator, usage):
    try:
        if not usage:
            return
        translator.token_count.inc(usage["total"])
        translator.prompt_token_count.inc(usage["prompt"])
        translator.completion_token_count.inc(usage["completion"])
        translator.cache_hit_prompt_token_count.inc(usage["cached"])
    except Exception as exc:  # usage statistics must never fail a translation
        logger.error(f"Error getting token usage: {exc}")


def install_relay_patch(options_path):
    """Patch OpenAITranslator in this process; return a restore callback."""
    options = load_relay_options(options_path)
    api_format = options["api_format"]

    import httpx
    import openai
    from pdf2zh_next.translator.translator_impl.openai import OpenAITranslator
    from tenacity import before_sleep_log
    from tenacity import retry
    from tenacity import retry_if_exception_type
    from tenacity import stop_after_attempt
    from tenacity import wait_exponential

    originals = {}
    for name in ("__init__", "do_translate", "do_llm_translate"):
        if name not in OpenAITranslator.__dict__:
            raise RuntimeError(
                "当前 pdf2zh_next 的 OpenAI 翻译器结构与预期不符"
                f"（缺少 {name}），自定义中转功能无法安全启用；"
                "翻译已在 API 调用前停止。"
            )
        originals[name] = OpenAITranslator.__dict__[name]
    if getattr(originals["__init__"], "_zotero_relay_patch", False):
        raise RuntimeError("自定义中转补丁重复安装，已停止以避免参数错误。")

    def configure(translator):
        for attribute in ("client", "model", "options"):
            if not hasattr(translator, attribute):
                raise RuntimeError(
                    "当前 pdf2zh_next 的 OpenAI 翻译器结构与预期不符"
                    f"（缺少 {attribute}），自定义中转功能无法安全启用。"
                )
        if options["extra_body"]:
            translator.add_cache_impact_parameters(
                "zotero_extra_body",
                json.dumps(options["extra_body"], sort_keys=True, ensure_ascii=False),
            )
        if api_format == FORMAT_CHAT:
            if options["headers"]:
                omit = getattr(openai, "Omit", None)
                custom = {}
                for name, value in options["headers"].items():
                    if value is None:
                        if omit is None:
                            raise RuntimeError(
                                "当前 openai 库版本不支持移除默认请求头（null 值）。"
                            )
                        value = omit()
                    custom[name] = value
                translator.client = translator.client.with_options(
                    default_headers=custom
                )
            if options["extra_body"]:
                merged = dict(translator.options.get("extra_body") or {})
                merged.update(options["extra_body"])
                translator.options["extra_body"] = merged
            return

        translator.add_cache_impact_parameters("zotero_api_format", api_format)
        timeout = getattr(translator, "timeout", None)
        translator._zotero_relay = {
            "api_format": api_format,
            "headers": options["headers"],
            "extra_body": options["extra_body"],
            "api_key": translator.client.api_key,
            "url": endpoint_url(translator.client.base_url, api_format),
            "client": httpx.Client(
                timeout=float(timeout) if timeout else DEFAULT_TIMEOUT_SECONDS,
                limits=httpx.Limits(
                    max_connections=None, max_keepalive_connections=None
                ),
            ),
        }

    def patched_init(self, *args, **kwargs):
        originals["__init__"](self, *args, **kwargs)
        configure(self)

    patched_init._zotero_relay_patch = True

    relay_retry = retry(
        retry=retry_if_exception_type(RelayRateLimitError),
        stop=stop_after_attempt(100),
        wait=wait_exponential(multiplier=1, min=1, max=15),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

    @relay_retry
    def call(translator, messages, rate_limit_params):
        json_mode = bool(
            getattr(translator, "enable_json_mode", False)
            and rate_limit_params
            and rate_limit_params.get("request_json_mode", False)
        )
        text, usage = _post(translator, messages, json_mode)
        _count_usage(translator, usage)
        if not text.strip():
            raise RelayError(
                "中转站返回成功，但响应里没有文本内容。"
                "请检查模型名称、接口类型是否与中转站匹配。"
            )
        return translator._remove_cot_content(text.strip())

    def patched_do_translate(self, text, rate_limit_params: dict = None):
        return call(self, self.prompt(text), rate_limit_params)

    def patched_do_llm_translate(self, text, rate_limit_params: dict = None):
        if text is None:
            return None
        return call(self, [{"role": "user", "content": text}], rate_limit_params)

    OpenAITranslator.__init__ = patched_init
    if api_format != FORMAT_CHAT:
        OpenAITranslator.do_translate = patched_do_translate
        OpenAITranslator.do_llm_translate = patched_do_llm_translate

    def restore():
        for name, original in originals.items():
            setattr(OpenAITranslator, name, original)

    logger.info("Custom relay enabled (%s)", describe_relay_options(options))
    return restore
