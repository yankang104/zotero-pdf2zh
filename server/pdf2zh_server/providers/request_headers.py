"""Build the HTTP headers used by custom translation services."""

import json
import re

HEADERS_FIELD = "zotero_extra_headers"
AUTH_MODE_FIELD = "zotero_auth_mode"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"

_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def parse_extra_headers(value) -> dict:
    """Parse the existing extraData header object, keeping its error messages."""
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
                f"{HEADERS_FIELD} 不是合法的 JSON: {exc}。"
                '正确写法示例: {"User-Agent": "my-client/1.0"}'
            ) from exc
    if not isinstance(value, dict):
        raise ValueError(f'{HEADERS_FIELD} 必须是 JSON 对象，例如 {{"名称": "值"}}。')

    headers = {}
    for name, raw in value.items():
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


def build_request_headers(
    api_format,
    api_key,
    custom_headers,
    stream=False,
    auth_mode="auto",
) -> dict:
    """Apply user overrides to automatic headers; None omits a header."""
    headers = {
        "content-type": ("Content-Type", "application/json"),
        "accept": ("Accept", "text/event-stream" if stream else "application/json"),
    }
    if auth_mode == "auto":
        auth_mode = "x-api-key" if api_format == "messages" else "bearer"

    credential = str(api_key or "")
    if auth_mode == "x-api-key":
        headers["x-api-key"] = ("x-api-key", credential)
    else:
        headers["authorization"] = ("Authorization", f"Bearer {credential}")

    if api_format == "messages":
        headers["anthropic-version"] = (
            "anthropic-version",
            DEFAULT_ANTHROPIC_VERSION,
        )

    for name, value in (custom_headers or {}).items():
        normalized_name = name.lower()
        if value is None:
            headers.pop(normalized_name, None)
        else:
            headers[normalized_name] = (name, value)

    return dict(headers.values())
