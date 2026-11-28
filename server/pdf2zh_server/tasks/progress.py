"""Translate engine output into task updates and retain diagnostic output tails."""

import collections
import re
import threading as _threading

_ENGINE_TAIL = collections.deque(maxlen=120)

_ENGINE_TAIL_LOCK = _threading.Lock()

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

_ANSI_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

_OSC_LEFTOVER_RE = re.compile(r"\]?8;;[^ ]*")

MAIN_PROGRESS_RE = re.compile(
    r"\btranslate\s+[^a-z\(\)\r\n]*?(\d+)/(\d+)\b", re.IGNORECASE
)

STEP_PROGRESS_RE = re.compile(r"(.+?)\(\d+/\d+\)\s+.*?(\d+)/(\d+)")

LEGACY_PROGRESS_RE = re.compile(
    r"(?:translate|Running|Parse).*?(\d+)/(\d+)", re.IGNORECASE
)

ANSI_ESCAPE = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")

PDF2ZH_TQDM_RE = re.compile(r"\|\s*(\d+)/(\d+)\s+\[")


def _record_engine_text(text):
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        with _ENGINE_TAIL_LOCK:
            _ENGINE_TAIL.append(line)


def recent_engine_output(n=40):
    """最近一次(或多次)引擎运行输出的尾部行, 供错误解读与诊断。"""
    with _ENGINE_TAIL_LOCK:
        items = list(_ENGINE_TAIL)
    return "\n".join(items[-n:])


def _clean_engine_line(line: str) -> str:
    line = _ANSI_OSC_RE.sub("", line)
    line = _ANSI_CSI_RE.sub("", line)
    line = _CONTROL_RE.sub("", line)
    line = _OSC_LEFTOVER_RE.sub("", line)
    return " ".join(line.split()).strip()


def engine_tail_for_error(max_lines: int = 5) -> str:
    """给用户看的引擎尾部: 只保留真正的错误行, 去掉进度条与转义码。"""
    with _ENGINE_TAIL_LOCK:
        items = list(_ENGINE_TAIL)
    picked = []
    for raw in reversed(items):
        if len(picked) >= max_lines:
            break
        cleaned = _clean_engine_line(raw)
        if not cleaned:
            continue
        lower = cleaned.lower()
        is_progress = ("━" in cleaned or "█" in cleaned) and "error" not in lower
        if is_progress:
            continue
        if (
            "error" in lower
            or "traceback" in lower
            or "exception" in lower
            or "warning" in lower
        ):
            picked.append(cleaned[:240])
    return "\n".join(reversed(picked))


def parse_progress(text):
    """Parse one engine output chunk into a task update."""
    clean = ANSI_ESCAPE.sub("", text)
    match = MAIN_PROGRESS_RE.search(clean)
    if match:
        curr, total = (int(match.group(1)), int(match.group(2)))
        if total > 0:
            pct = int(curr / total * 100)
            return {
                "progress": pct,
                "status": "running",
                "message": f"translate {curr}/{total}",
            }
        return
    match = STEP_PROGRESS_RE.search(clean)
    if match:
        step_name = match.group(1).strip()
        return {"status": "running", "message": step_name}
    tqdm_matches = PDF2ZH_TQDM_RE.findall(clean)
    if tqdm_matches:
        curr, total = (int(tqdm_matches[-1][0]), int(tqdm_matches[-1][1]))
        if total > 0:
            return {
                "progress": int(curr / total * 100),
                "status": "running",
                "message": f"translate {curr}/{total}",
            }
    match = LEGACY_PROGRESS_RE.search(clean)
    if match:
        curr, total = (int(match.group(1)), int(match.group(2)))
        if total > 0:
            pct = int(curr / total * 100)
            return {"progress": pct, "status": "running"}


def report_progress(text, on_progress):
    if on_progress is not None:
        updates = parse_progress(text)
        if updates:
            on_progress(updates)
