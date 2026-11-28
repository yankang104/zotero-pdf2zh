"""Extract relay request settings while leaving engine parameters in extraData."""

from __future__ import annotations

from pdf2zh_server.providers.request_body import parse_extra_body
from pdf2zh_server.providers.request_headers import parse_extra_headers

FORMAT_FIELD = "zotero_api_format"
HEADERS_FIELD = "zotero_extra_headers"
BODY_FIELD = "zotero_extra_body"
AUTH_MODE_FIELD = "zotero_auth_mode"
BODY_TEMPLATE_FIELD = "zotero_body_template"
RELAY_FIELDS = (
    FORMAT_FIELD,
    HEADERS_FIELD,
    BODY_FIELD,
    AUTH_MODE_FIELD,
    BODY_TEMPLATE_FIELD,
)

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


def parse_api_format(value) -> str:
    """Resolve the interface aliases already accepted by the relay settings."""
    text = str(value or "").strip().lower().strip("/")
    if text.startswith("v1/"):
        text = text[3:]
    if text not in _FORMAT_ALIASES:
        raise ValueError(
            f"接口类型 {FORMAT_FIELD} 只能是 chat / responses / messages，"
            f"收到的是: {value!r}"
        )
    return _FORMAT_ALIASES[text]


def normalize_relay_options(extra_data) -> dict | None:
    """Consume request fields; keep ordinary translator parameters unchanged.

    Explicit extra-body overrides remain in extra_body. The effective API
    version comes from the final headers when constructing the request.
    """
    if not isinstance(extra_data, dict):
        return None

    raw_format = extra_data.pop(FORMAT_FIELD, None)
    raw_headers = extra_data.pop(HEADERS_FIELD, None)
    raw_body = extra_data.pop(BODY_FIELD, None)
    auth_mode = str(extra_data.pop(AUTH_MODE_FIELD, None) or "auto").strip().lower()
    body_template = (
        str(extra_data.pop(BODY_TEMPLATE_FIELD, None) or "standard").strip().lower()
    )

    options = {
        "api_format": parse_api_format(raw_format),
        "headers": parse_extra_headers(raw_headers),
        "extra_body": parse_extra_body(raw_body),
    }
    if auth_mode != "auto":
        options["auth_mode"] = auth_mode
    if body_template != "standard":
        options["body_template"] = body_template

    if (
        options["api_format"] == FORMAT_CHAT
        and not options["headers"]
        and not options["extra_body"]
        and auth_mode == "auto"
        and body_template == "standard"
    ):
        return None
    return options
