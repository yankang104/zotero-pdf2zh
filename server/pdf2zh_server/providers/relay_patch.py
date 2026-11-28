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

import hashlib
import json
import logging
import os
import re
import threading

from pdf2zh_server.providers.relay_options import (
    FORMAT_CHAT,
    FORMAT_MESSAGES,
    FORMAT_RESPONSES,
    parse_api_format,
)
from pdf2zh_server.providers.request_body import (
    build_request_body,
    parse_extra_body,
)
from pdf2zh_server.providers.request_headers import (
    DEFAULT_ANTHROPIC_VERSION as ANTHROPIC_VERSION,
)
from pdf2zh_server.providers.request_headers import (
    build_request_headers as build_headers,
)
from pdf2zh_server.providers.request_headers import (
    parse_extra_headers,
)

logger = logging.getLogger(__name__)

RELAY_PATCH_FLAG = "--zotero-relay-patch"

DEFAULT_TIMEOUT_SECONDS = 600.0

_VERSION_SUFFIX = re.compile(r"/v\d+[a-z0-9]*$", re.IGNORECASE)


# --------------------------------------------------------------------------
# Option parsing (Server process and engine process)
# --------------------------------------------------------------------------


def write_relay_options(path, options) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(options, handle, ensure_ascii=False)


def _translator_identity(base_url, model, api_key) -> dict:
    base = str(base_url or "").strip()
    if base.lower() in {"", "null", "none"}:
        base = os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    base = base.strip().rstrip("/")
    # Upstream validates and removes this suffix before creating its client.
    base = re.sub(r"/chat/completions$", "", base).rstrip("/")
    return {
        "base_url": base,
        "model": str(model or "gpt-4o-mini").strip(),
        "api_key_hash": hashlib.sha256(str(api_key or "").encode("utf-8")).hexdigest(),
    }


def bind_relay_target(options, *, base_url, model, api_key, service=""):
    """Bind a job's relay options to its main translator, without storing a key.

    Call this with the effective saved configuration, after blank request
    fields have been resolved. An independently configured term translator
    must keep its own transport, headers and request body.
    """
    if options is None:
        return None
    bound = dict(options)
    bound["target"] = {
        **_translator_identity(base_url, model, api_key),
        "service": str(service or "").strip(),
    }
    return bound


def load_relay_options(path) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    options = {
        "api_format": parse_api_format(data.get("api_format")),
        "headers": parse_extra_headers(data.get("headers")),
        "extra_body": parse_extra_body(data.get("extra_body")),
    }
    options.update(
        {name: data[name] for name in ("auth_mode", "body_template") if name in data}
    )
    target = data.get("target")
    if target is not None:
        if (
            not isinstance(target, dict)
            or not isinstance(target.get("base_url"), str)
            or not isinstance(target.get("model"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", str(target.get("api_key_hash") or ""))
        ):
            raise ValueError("自定义中转目标配置不完整，请更新 Server 后重新提交任务。")
        options["target"] = {
            "base_url": target["base_url"].strip().rstrip("/"),
            "model": target["model"].strip(),
            "api_key_hash": target["api_key_hash"],
            "service": str(target.get("service") or "").strip(),
        }
    return options


def relay_cache_namespace(options, identity) -> str:
    """Separate providers and credentials using a hash, never plaintext headers."""
    namespace = {
        "identity": identity,
        "service": options.get("target", {}).get("service", ""),
        "api_format": options["api_format"],
        "auth_mode": options.get("auth_mode", "auto"),
        "body_template": options.get("body_template", "standard"),
        "headers": {name.lower(): value for name, value in options["headers"].items()},
        "extra_body": options["extra_body"],
    }
    encoded = json.dumps(
        namespace, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def describe_relay_options(options) -> str:
    """Log-safe summary: header and body *names* only, never their values."""
    return (
        f"format={options['api_format']}, "
        f"auth={options.get('auth_mode', 'auto')}, "
        f"template={options.get('body_template', 'standard')}, "
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
    if api_format == FORMAT_CHAT:
        return (
            base if base.endswith("/chat/completions") else base + "/chat/completions"
        )
    if api_format == FORMAT_RESPONSES:
        return base if base.endswith("/responses") else base + "/responses"
    if api_format == FORMAT_MESSAGES:
        if base.endswith("/messages"):
            return base
        if _VERSION_SUFFIX.search(base):
            return base + "/messages"
        return base + "/v1/messages"
    raise ValueError(f"Unsupported relay format: {api_format}")


def build_body(
    api_format,
    model,
    messages,
    options,
    extra_body,
    json_mode=False,
    *,
    template="standard",
    api_version=ANTHROPIC_VERSION,
):
    """Keep the previous entry point while delegating request-body generation."""
    return build_request_body(
        api_format,
        model,
        messages,
        options,
        extra_body,
        json_mode=json_mode,
        template=template,
        api_version=api_version,
    )


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
    kind = (
        str(error.get("type") or error.get("code") or "")
        if isinstance(error, dict)
        else ""
    )
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


def _chat_text(data: dict) -> str:
    choice = next(iter(data.get("choices") or []), {})
    return str((choice.get("message") or {}).get("content") or "")


def _usage(api_format: str, usage) -> dict:
    """Normalize token usage to {prompt, completion, total, cached}."""
    if not isinstance(usage, dict):
        return {}

    def count(value):
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError, OverflowError):
            return 0

    if api_format == FORMAT_CHAT:
        prompt = count(usage.get("prompt_tokens"))
        completion = count(usage.get("completion_tokens"))
        details = usage.get("prompt_tokens_details") or {}
        cached = usage.get("prompt_cache_hit_tokens") or details.get("cached_tokens")
    else:
        prompt = count(usage.get("input_tokens"))
        completion = count(usage.get("output_tokens"))
    if api_format == FORMAT_RESPONSES:
        details = usage.get("input_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, dict) else 0
    elif api_format == FORMAT_MESSAGES:
        cached = usage.get("cache_read_input_tokens")
    return {
        "prompt": prompt,
        "completion": completion,
        "total": count(usage.get("total_tokens")) or (prompt + completion),
        "cached": count(cached),
    }


def parse_json_response(api_format: str, data):
    """Return (text, usage) from a non-streaming response body."""
    if not isinstance(data, dict):
        raise RelayError("中转站返回的不是 JSON 对象。")
    if data.get("error") or data.get("type") == "error":
        _raise_api_error(data.get("error") or data)
    if api_format == FORMAT_CHAT:
        text = _chat_text(data)
    elif api_format == FORMAT_RESPONSES:
        _validate_responses_completion(data)
        text = _responses_text(data)
    elif api_format == FORMAT_MESSAGES:
        _validate_messages_completion(data.get("stop_reason"))
        text = _messages_text(data)
    else:
        raise ValueError(f"Unsupported relay format: {api_format}")
    return text, _usage(api_format, data.get("usage"))


def _validate_responses_completion(response):
    if not isinstance(response, dict):
        raise RelayError("Responses 接口没有返回完整的完成回执。")
    if response.get("error"):
        _raise_api_error(response["error"])
    status = response.get("status")
    if status == "completed":
        return
    if status == "incomplete":
        details = response.get("incomplete_details") or {}
        reason = str(details.get("reason") or "") if isinstance(details, dict) else ""
        hint = (
            "请提高 max_output_tokens 后重试。"
            if reason == "max_output_tokens"
            else "请检查模型输出限制后重试。"
        )
        raise RelayError(
            f"Responses 输出未完成（incomplete{': ' + reason if reason else ''}）；{hint}"
        )
    raise RelayError(
        f"Responses 接口未确认输出完成（status={status or '缺失'}），"
        "已拒绝使用可能截断的译文。"
    )


def _validate_messages_completion(stop_reason):
    if isinstance(stop_reason, str) and stop_reason in {"end_turn", "stop_sequence"}:
        return
    if stop_reason == "max_tokens":
        raise RelayError(
            "Messages 输出达到 max_tokens 上限，译文可能截断；请提高 max_tokens 后重试。"
        )
    raise RelayError(
        f"Messages 接口未正常结束（stop_reason={stop_reason or '缺失'}），"
        "已拒绝使用未完成的译文。"
    )


def _sse_events(lines):
    """Decode SSE records, joining all data lines inside a single event."""
    data_lines = []
    event_name = ""
    first_line = True

    def decode_event():
        payload = "\n".join(data_lines)
        if not payload or payload == "[DONE]":
            return None
        try:
            event = json.loads(payload)
        except ValueError as exc:
            raise RelayError(
                "中转站的流式事件不是完整、合法的 JSON，译文可能截断。"
            ) from exc
        if not isinstance(event, dict):
            raise RelayError("中转站的流式事件不是 JSON 对象。")
        if not event.get("type") and event_name:
            event["type"] = event_name
        return event

    for raw_line in lines:
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8", "replace")
        line = str(raw_line).rstrip("\r\n")
        if first_line:
            line = line.lstrip("\ufeff")
            first_line = False
        if not line:
            event = decode_event()
            if event is not None:
                yield event
            data_lines = []
            event_name = ""
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "data":
            data_lines.append(value)
        elif field == "event":
            event_name = value
    # Some relays omit the final blank line. A complete terminal JSON record is
    # still usable; a final delta without a terminal record is rejected below.
    event = decode_event()
    if event is not None:
        yield event


def parse_sse_lines(api_format: str, lines):
    """Return (text, usage) from Server-Sent-Events lines."""
    parts = []
    usage = {}
    final = None
    completed = False
    stop_reason = None
    for event in _sse_events(lines):
        kind = event.get("type") or ""
        if kind == "error" or event.get("error"):
            _raise_api_error(event.get("error") or event)
        if api_format == FORMAT_CHAT:
            for choice in event.get("choices") or []:
                parts.append(str((choice.get("delta") or {}).get("content") or ""))
            usage = _usage(api_format, event.get("usage")) or usage
        elif api_format == FORMAT_RESPONSES:
            if kind == "response.output_text.delta":
                parts.append(str(event.get("delta") or ""))
            elif kind == "response.completed":
                final = event.get("response")
                _validate_responses_completion(final)
                usage = _usage(api_format, final.get("usage"))
                completed = True
            elif kind == "response.incomplete":
                response = event.get("response")
                if not isinstance(response, dict):
                    response = {}
                _validate_responses_completion({**response, "status": "incomplete"})
            elif kind == "response.failed":
                response = event.get("response") or {}
                _raise_api_error(response.get("error") or "response.failed")
        elif api_format == FORMAT_MESSAGES:
            if kind == "content_block_start":
                block = event.get("content_block") or {}
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            elif kind == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta":
                    parts.append(str(delta.get("text") or ""))
            elif kind == "message_start":
                message = event.get("message") or {}
                usage = _usage(api_format, message.get("usage"))
            elif kind == "message_delta":
                delta = event.get("delta") or {}
                if delta.get("stop_reason") is not None:
                    stop_reason = delta["stop_reason"]
                extra = _usage(api_format, event.get("usage"))
                if extra:
                    prompt = extra["prompt"] or usage.get("prompt", 0)
                    usage = {
                        "prompt": prompt,
                        "completion": extra["completion"],
                        "total": prompt + extra["completion"],
                        "cached": extra["cached"] or usage.get("cached", 0),
                    }
            elif kind == "message_stop":
                _validate_messages_completion(stop_reason)
                completed = True
        else:
            raise ValueError(f"Unsupported relay format: {api_format}")
    if api_format != FORMAT_CHAT and not completed:
        raise RelayError(
            "中转站的流式响应没有完成事件，连接可能中断；已拒绝使用截断的译文。"
        )
    text = "".join(parts)
    if final:
        text = _responses_text(final) or text
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
    api_version = {name.lower(): value for name, value in state["headers"].items()}.get(
        "anthropic-version", ANTHROPIC_VERSION
    )
    body = build_body(
        api_format,
        translator.model,
        messages,
        translator.options,
        state["extra_body"],
        json_mode=json_mode,
        template=state["body_template"],
        api_version=api_version,
    )
    stream = bool(body.get("stream"))
    headers = build_headers(
        api_format,
        state["api_key"],
        state["headers"],
        stream,
        auth_mode=state["auth_mode"],
    )
    client = state["client"]

    if stream:
        with client.stream(
            "POST", state["url"], headers=headers, json=body
        ) as response:
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
        raise RelayError("中转站返回的内容不是 JSON: " + response.text[:300]) from exc
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
    auth_mode = options.get("auth_mode", "auto")
    body_template = options.get("body_template", "standard")

    import httpx
    import openai
    from pdf2zh_next.translator.translator_impl.openai import OpenAITranslator
    from tenacity import (
        before_sleep_log,
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )

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

    selected_identity = options.get("target")
    selected_engine_settings = None
    identity_lock = threading.Lock()
    owned_clients = []

    def configure(translator, settings):
        nonlocal selected_identity, selected_engine_settings
        for attribute in ("client", "model", "options"):
            if not hasattr(translator, attribute):
                raise RuntimeError(
                    "当前 pdf2zh_next 的 OpenAI 翻译器结构与预期不符"
                    f"（缺少 {attribute}），自定义中转功能无法安全启用。"
                )
        identity = _translator_identity(
            translator.client.base_url, translator.model, translator.client.api_key
        )
        with identity_lock:
            # Older Server sidecars have no target. The main translator is
            # constructed first by create_babeldoc_config(); bind it once, then
            # leave any separately configured term translator untouched.
            if selected_identity is None:
                selected_identity = identity
            if any(
                identity[key] != selected_identity[key]
                for key in ("base_url", "model", "api_key_hash")
            ):
                if selected_engine_settings is None:
                    raise RuntimeError(
                        "自定义中转目标与正文翻译器配置不一致，"
                        "本次没有发起 API 请求；请重新保存配置后重试。"
                    )
                return
            engine_settings = getattr(settings, "translate_engine_settings", None)
            if engine_settings is None:
                raise RuntimeError("当前翻译器缺少配置实例，自定义中转无法安全绑定。")
            if selected_engine_settings is None:
                selected_engine_settings = engine_settings
            elif engine_settings is not selected_engine_settings:
                # Equal endpoint/model/key values can still belong to a
                # separately configured term engine. Follow the main settings
                # object, not merely provider credentials.
                return

        translator.add_cache_impact_parameters(
            "zotero_relay_namespace", relay_cache_namespace(options, identity)
        )
        chat_stream = options["extra_body"].get(
            "stream",
            (translator.options.get("extra_body") or {}).get(
                "stream", translator.options.get("stream", False)
            ),
        )
        if (
            api_format == FORMAT_CHAT
            and body_template == "standard"
            and not chat_stream
        ):
            if options["headers"] or auth_mode != "auto":
                omit = getattr(openai, "Omit", None)
                custom = {
                    name.lower(): value
                    for name, value in build_headers(
                        api_format,
                        translator.client.api_key,
                        options["headers"],
                        auth_mode=auth_mode,
                    ).items()
                }
                custom.update(
                    {
                        name.lower(): None
                        for name, value in options["headers"].items()
                        if value is None
                    }
                )
                if "authorization" not in custom:
                    custom["authorization"] = None
                authorization_omitted = custom["authorization"] is None
                sdk_header_names = {
                    name.lower(): name for name in translator.client.default_headers
                }
                sdk_header_names["authorization"] = "Authorization"
                custom = {
                    sdk_header_names.get(name, name): value
                    for name, value in custom.items()
                }
                for name, value in list(custom.items()):
                    if value is None:
                        if omit is None:
                            raise RuntimeError(
                                "当前 openai 库版本不支持移除默认请求头（null 值）。"
                            )
                        value = omit()
                    custom[name] = value
                if authorization_omitted:
                    translator.options["extra_headers"] = {
                        **(translator.options.get("extra_headers") or {}),
                        "Authorization": custom["Authorization"],
                    }
                translator.client = translator.client.with_options(
                    default_headers=custom
                )
            if options["extra_body"]:
                merged = dict(translator.options.get("extra_body") or {})
                merged.update(options["extra_body"])
                translator.options["extra_body"] = merged
            return

        timeout = getattr(translator, "timeout", None)
        client = httpx.Client(
            timeout=float(timeout) if timeout else DEFAULT_TIMEOUT_SECONDS,
            limits=httpx.Limits(max_connections=None, max_keepalive_connections=None),
        )
        with identity_lock:
            owned_clients.append(client)
        translator._zotero_relay = {
            "api_format": api_format,
            "auth_mode": auth_mode,
            "body_template": body_template,
            "headers": options["headers"],
            "extra_body": options["extra_body"],
            "api_key": translator.client.api_key,
            "url": endpoint_url(translator.client.base_url, api_format),
            "client": client,
        }

    def patched_init(self, *args, **kwargs):
        originals["__init__"](self, *args, **kwargs)
        settings = args[0] if args else kwargs.get("settings")
        configure(self, settings)

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
        translated = translator._remove_cot_content(text.strip()).strip()
        if not translated:
            raise RelayError(
                "中转站只返回了思考内容，没有可用译文；请检查模型和接口类型。"
            )
        return translated

    def patched_do_translate(self, text, rate_limit_params: dict = None):
        if not hasattr(self, "_zotero_relay"):
            return originals["do_translate"](self, text, rate_limit_params)
        return call(self, self.prompt(text), rate_limit_params)

    def patched_do_llm_translate(self, text, rate_limit_params: dict = None):
        if not hasattr(self, "_zotero_relay"):
            return originals["do_llm_translate"](self, text, rate_limit_params)
        if text is None:
            return None
        return call(self, [{"role": "user", "content": text}], rate_limit_params)

    OpenAITranslator.__init__ = patched_init
    OpenAITranslator.do_translate = patched_do_translate
    OpenAITranslator.do_llm_translate = patched_do_llm_translate

    def restore():
        for name, original in originals.items():
            setattr(OpenAITranslator, name, original)
        with identity_lock:
            clients = list(owned_clients)
            owned_clients.clear()
        for client in clients:
            try:
                client.close()
            except Exception as exc:
                logger.warning(
                    "关闭自定义中转 HTTP 客户端失败（%s）", type(exc).__name__
                )

    logger.info("Custom relay enabled (%s)", describe_relay_options(options))
    return restore
