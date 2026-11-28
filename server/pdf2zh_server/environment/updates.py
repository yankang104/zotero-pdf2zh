from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from pdf2zh_server.environment.discovery import (
    find_existing_environment,
    managed_python_env,
    pdf2zh_next_meets_minimum,
    read_versions,
    runtime_supports_deepseek_thinking,
)
from pdf2zh_server.environment.install import transactional_install_or_update
from pdf2zh_server.paths import SERVER_ROOT


def server_version_from_source() -> str:
    try:
        text = (SERVER_ROOT / "server.py").read_text(encoding="utf-8")
        match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        return match.group(1) if match else "unknown"
    except Exception:
        return "unknown"


def package_update_state_path() -> Path:
    return SERVER_ROOT / "config" / "package_update_state.json"


def read_package_update_state() -> dict:
    try:
        with package_update_state_path().open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def write_package_update_state(server_version: str, status: str) -> None:
    path = package_update_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(
            {"server_version": server_version, "status": status},
            handle,
            ensure_ascii=False,
            indent=2,
        )
    os.replace(temp, path)


def _server_cli_bool(name: str, default: bool = False) -> bool:
    flag = "--" + name
    args = sys.argv[1:]
    for index, value in enumerate(args):
        if value == flag and index + 1 < len(args):
            return str(args[index + 1]).strip().lower() in {"1", "true", "yes", "y"}
        prefix = flag + "="
        if value.startswith(prefix):
            return value[len(prefix) :].strip().lower() in {"1", "true", "yes", "y"}
    return default


def maybe_prompt_existing_user_update(
    *,
    env_tool: str = "auto",
    config_path: str | os.PathLike[str] | None = None,
    preferred_index: str | None = None,
) -> None:
    if not sys.stdin or not sys.stdin.isatty() or _server_cli_bool("enable_winexe"):
        return
    existing = find_existing_environment("pdf2zh_next", env_tool)
    if not existing:
        return
    server_version = server_version_from_source()
    state = read_package_update_state()
    if state.get("server_version") == server_version and state.get("status") in {
        "success",
        "declined",
        "failed",
        "skipped",
    }:
        return
    try:
        versions = read_versions(existing[2], "pdf2zh_next")
        current = versions.get("pdf2zh-next") or "unknown"
    except Exception:
        current = "unknown"
    if pdf2zh_next_meets_minimum(current):
        write_package_update_state(server_version, "skipped")
        print(f"✅ 当前 pdf2zh_next {current} 已满足 >=2.9.0，跳过启动时环境更新。")
        return
    has_thinking = runtime_supports_deepseek_thinking(
        existing[2],
        env=managed_python_env(),
        isolated=True,
    )
    print("\n" + "─" * 60)
    print("🔄 检测到已有 Python 翻译环境")
    print(f"当前 pdf2zh_next: {current}")
    if has_thinking:
        print("当前环境已支持 DeepSeek V4 思考控制；仍可检查其他兼容依赖更新。")
    else:
        print(
            f"Zotero PDF2zh v{server_version} 的 DeepSeek V4 思考控制需要新版运行时。"
        )
    print("更新会在当前 conda/uv 环境中直接安装依赖，不再创建 staging 或 backup 环境。")
    print("\n[Y] 检查并更新（推荐）")
    print("[N] 暂不更新")
    try:
        answer = input("\n选择 [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    if answer in {"", "y", "yes"}:
        success, _, _ = transactional_install_or_update(
            "pdf2zh_next",
            env_tool=existing[0],
            config_path=config_path,
            preferred_index=preferred_index,
            require_deepseek_thinking=True,
        )
        write_package_update_state(server_version, "success" if success else "failed")
        if not success:
            print(
                "⚠️ 本次更新未完成。"
                "本版本不会再次自动询问，可稍后运行 python update_packages.py 重试。"
            )
    else:
        write_package_update_state(server_version, "declined")
        print("👌 已保留当前翻译环境；本 Server 版本不会再次询问。")
