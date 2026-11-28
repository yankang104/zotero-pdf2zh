"""用户可见错误分类：把引擎/上游的技术报错翻译成用户能看懂的提示。

规则移植自 zotero-omni-translate 的 error_catalog，并针对本项目的
BabelDOC / pdf2zh_next 报错补充规则（如扫描件、CID 字符）。
原始错误始终保留在日志与 message 字段中，这里只做附加解读。
"""

from __future__ import annotations

import re
from typing import Callable, Optional

MatchFn = Callable[[str, str], bool]


def _any(lower: str, *parts: str) -> bool:
    return any(part in lower for part in parts)


def _rule(code: str, user: str, hint: str, match: MatchFn) -> dict:
    return {"code": code, "user": user, "hint": hint, "match": match}


# 起步原则: 只收录经用户真实报错验证过的案例, 宁缺勿滥——
# 错误的解读比没有解读更糟。新规则需先拿到真实错误文本再添加。
ERROR_RULES: list[dict] = [
    _rule(
        "BITSTRING_INCOMPATIBLE",
        "翻译引擎无法导入 BitStream，通常是 bitstring 依赖版本不兼容。",
        "请在 Server 目录执行 python manage_packages.py doctor，"
        "并检查所用环境中的 bitstring 是否为 >=4.3.0,<5。",
        lambda t, l: (
            ("cannot import name 'bitstream'" in l and "bitstring" in l)
            or ("no module named 'bitstring'" in l)
        ),
    ),
    _rule(
        "API_RATE_LIMIT",
        "翻译服务返回请求频率限制（HTTP 429）。",
        "请检查 API 服务的额度与 QPS 设置，适当降低并发后重试。",
        lambda t, l: bool(
            re.search(r"\b(?:http|status(?:\s+code)?|error\s+code)\s*[:=]?\s*429\b", l)
            or "429 too many requests" in l
            or "rate_limit_exceeded" in l
        ),
    ),
    _rule(
        "API_AUTH_FAILED",
        "翻译服务拒绝了身份认证（API Key 或访问权限可能有问题）。",
        "请核对服务商、API Key 和模型访问权限；不要把完整密钥发到群里。",
        lambda t, l: (
            "invalid_api_key" in l
            or "incorrect api key provided" in l
            or "401 unauthorized" in l
        ),
    ),
    _rule(
        "PDF_UNREADABLE_TEXT",
        "这份 PDF 读不出可翻译的文字（扫描件没有文字层，或内嵌字体编码异常）。",
        "请换一份带文字层的 PDF（出版社原版通常可以），"
        "或先用 OCR 工具转成文字版再翻译。",
        lambda t, l: _any(
            l,
            "too many cid chars",
            "contains no graphs",
            "no extractable text",
            "scanned pdf",
            "no text layer",
            "without text layer",
            "没有可提取的文本",
        ),
    ),
]


def classify_error_message(message: Optional[str]) -> dict:
    text = str(message or "").strip()
    lower = text.lower()
    info = {
        "errorCode": "UNKNOWN_ERROR",
        "userMessage": "",
        "hint": "",
    }
    if not text:
        return info
    for rule in ERROR_RULES:
        try:
            matched = rule["match"](text, lower)
        except Exception:
            matched = False
        if matched:
            info["errorCode"] = rule["code"]
            info["userMessage"] = rule["user"]
            info["hint"] = rule["hint"]
            return info
    return info


def classify_error_blob(blob: Optional[str]) -> dict:
    """从多行引擎日志中提取最相关的一条用户提示。

    优先对含错误关键词的行逐行匹配，再退回对整段文本匹配。
    """
    if not blob:
        return classify_error_message(None)
    interesting = []
    for raw in str(blob).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("File ", "Traceback", "return ", "raise ")):
            continue
        if "site-packages" in line and ".py" in line:
            continue
        interesting.append(line)
    # 真正的报错通常在日志末尾，从最后一行往前匹配。
    for line in reversed(interesting):
        lowered = line.lower()
        for rule in ERROR_RULES:
            try:
                matched = rule["match"](line, lowered)
            except Exception:
                matched = False
            if matched:
                return {
                    "errorCode": rule["code"],
                    "userMessage": rule["user"],
                    "hint": rule["hint"],
                }
    # 兜底：整段拼接再匹配一次（覆盖跨行错误文本）。
    return classify_error_message(" | ".join(interesting[-30:]))


import subprocess
import traceback

from pdf2zh_server.tasks.progress import recent_engine_output

_VALUE_ERROR_RE = re.compile(r"(?m)^ValueError:\s*(?P<msg>.+)$")


def classify_exception(exc):
    """从异常（优先引擎 stderr）提取用户可读的错误解读。"""
    try:
        blob = ""
        if isinstance(exc, subprocess.CalledProcessError) and getattr(
            exc, "stderr", None
        ):
            blob = str(exc.stderr)
        blob = blob or str(exc)
        blob = f"{blob}\n{recent_engine_output(30)}"
        return classify_error_blob(blob)
    except Exception:
        return {"errorCode": "UNKNOWN_ERROR"}


def exception_payload(exc, context=None):
    if context:
        print(f"⚠️ [Zotero PDF2zh Server] {context} Error: {exc}")
    else:
        print(f"⚠️ [Zotero PDF2zh Server] Error: {exc}")
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    info = derive_error_info(exc)
    payload = {"status": "error", "ok": False, "message": info["message"]}
    classified = classify_exception(exc)
    if classified.get("errorCode") not in (None, "", "UNKNOWN_ERROR"):
        payload["errorCode"] = classified["errorCode"]
        payload["userMessage"] = classified["userMessage"]
        payload["hint"] = classified["hint"]
        print(
            f"💡 [Zotero PDF2zh Server] 错误解读: [{classified['errorCode']}] {classified['userMessage']}"
        )
    error_type = info.get("errorType")
    if error_type:
        payload["errorType"] = error_type
    if isinstance(exc, subprocess.CalledProcessError):
        payload["exitCode"] = exc.returncode
    return payload


def derive_error_info(exc):
    parts = []
    if isinstance(exc, subprocess.CalledProcessError) and getattr(exc, "stderr", None):
        parts.append(exc.stderr)
    formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    if formatted:
        parts.append(formatted)
    blob = "\n".join((part for part in parts if part))
    ve_msg = extract_value_error(blob)
    if ve_msg:
        return {"errorType": "ValueError", "message": ve_msg}

    def _tail_readable(text):
        lines = [ln.rstrip() for ln in text.splitlines()]
        for ln in reversed(lines):
            if not ln:
                continue
            if ln.startswith(("Traceback", "File ")):
                continue
            return ln
        return str(exc).strip() or exc.__class__.__name__

    fallback_message = (
        _tail_readable(blob) if blob else str(exc).strip() or exc.__class__.__name__
    )
    return {"errorType": exc.__class__.__name__, "message": fallback_message}


def extract_value_error(blob):
    if not blob:
        return None
    if not isinstance(blob, str):
        blob = str(blob)
    matches = list(_VALUE_ERROR_RE.finditer(blob))
    if not matches:
        return None
    match = matches[-1]
    msg = match.group("msg").strip()
    tail_lines = []
    for line in blob[match.end() :].splitlines():
        if not line:
            break
        if line.startswith("Traceback") or _VALUE_ERROR_RE.match(line):
            break
        if line[:1] in (" ", "\t") or line.startswith("^"):
            tail_lines.append(line.strip())
        else:
            break
    if tail_lines:
        msg += " " + " ".join(tail_lines)
    return msg or None
