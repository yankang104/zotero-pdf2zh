"""Fetch model IDs with the API settings currently entered in the editor."""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


def model_list_url(base_url: str, service: str, api_format: str = "chat") -> str:
    """Resolve a model-list URL from a service base or translation endpoint."""
    base_url = base_url.strip()
    if service in {
        "bing",
        "google",
        "argos",
        "claudecode",
        "deepl",
        "tencent",
        "tencentmechinetranslation",
        "azure",
        "dify",
        "anythingllm",
    }:
        raise ValueError("该服务没有 HTTP 模型目录，请手动填写模型名称。")
    if not base_url:
        raise ValueError("请先填写模型接口的 URL。")
    parsed = urlsplit(base_url)
    path = parsed.path.rstrip("/")
    if service == "ollama":
        path = re.sub(
            r"/(?:api/tags|api/generate|api/chat|v1(?:/models|/chat/completions)?)$",
            "",
            path,
        )
        path += "/tags" if path.endswith("/api") else "/api/tags"
    else:
        path = re.sub(r"/(?:chat/completions|responses|messages)$", "", path)
        if not path.endswith("/models"):
            if (
                service == "xinference"
                or (api_format == "messages" and service != "gemini")
            ) and not re.search(r"/v\d+[a-z0-9]*$", path, re.IGNORECASE):
                path += "/v1"
            path += "/models"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def extract_model_ids(payload) -> list[str]:
    """Read the model-list shapes already supported by the plugin."""
    if isinstance(payload, list):
        model_entries = payload
    elif isinstance(payload, dict):
        result = payload.get("result")
        candidates = (
            payload.get("data"),
            payload.get("models"),
            result.get("data") if isinstance(result, dict) else None,
            result,
        )
        model_entries = next(
            (entries for entries in candidates if isinstance(entries, list)), []
        )
    else:
        return []

    model_ids = {}
    for entry in model_entries:
        if isinstance(entry, str):
            model_id = entry
        elif isinstance(entry, dict):
            model_id = (
                entry.get("id")
                or entry.get("name")
                or entry.get("model")
                or entry.get("model_name")
                or ""
            )
        else:
            continue
        model_id = str(model_id)
        if model_id.startswith("models/"):
            model_id = model_id[len("models/") :]
        if model_id:
            model_ids[model_id] = None
    return list(model_ids)


def fetch_model_ids(
    base_url: str,
    request_headers: dict[str, str],
    *,
    service: str,
    api_format: str = "chat",
    api_key: str = "",
) -> list[str]:
    """GET model IDs using final headers; let the caller handle request errors."""
    url = model_list_url(base_url, service, api_format)
    request = Request(url, headers=request_headers, method="GET")
    with urlopen(request, timeout=20) as response:
        return extract_model_ids(json.load(response))
