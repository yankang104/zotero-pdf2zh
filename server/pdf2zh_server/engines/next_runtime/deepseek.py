from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import toml

from pdf2zh_server.providers.deepseek_options import (
    _RUNTIME_CAPABILITY_CACHE,
    DEEPSEEK_EFFORT_VALUES,
    FLASH_PATCH_FLAG,
    REASONING_EFFORT_FIELD,
    REASONING_EFFORT_FLAG,
    THINKING_MODE_FIELD,
    THINKING_MODE_FLAG,
    is_deepseek_flash_model,
    is_deepseek_thinking_model,
    resolved_thinking_mode,
    thinking_runtime_policy,
)


def strip_thinking_fields_from_config(config_path: str) -> None:
    """Best-effort rollback for runtimes that do not understand V4 fields."""
    try:
        config_data = toml.load(config_path)
        detail = config_data.get("deepseek_detail")
        if not isinstance(detail, dict):
            return
        changed = False
        for key in (THINKING_MODE_FIELD, REASONING_EFFORT_FIELD):
            if key in detail:
                detail.pop(key, None)
                changed = True
        if changed:
            with open(config_path, "w", encoding="utf-8") as handle:
                toml.dump(config_data, handle)
            print(
                "🧹 [DeepSeek V4] 当前运行时不支持思考控制；"
                "已从 config.toml 移除仅新版本支持的字段。"
            )
    except Exception as exc:
        print(f"⚠️ [DeepSeek V4] 清理不兼容配置字段失败: {exc}")


def _option_value(cmd: list[str], flag: str) -> str | None:
    for index, value in enumerate(cmd):
        if value == flag and index + 1 < len(cmd):
            return str(cmd[index + 1])
        prefix = flag + "="
        if value.startswith(prefix):
            return value[len(prefix) :]
    return None


def _remove_option(cmd: list[str], flag: str) -> list[str]:
    result: list[str] = []
    index = 0
    prefix = flag + "="
    while index < len(cmd):
        value = cmd[index]
        if value == flag:
            index += 2 if index + 1 < len(cmd) else 1
            continue
        if value.startswith(prefix):
            index += 1
            continue
        result.append(value)
        index += 1
    return result


def _invocation_prefix(final_cmd: list[str]) -> list[str]:
    """Return the exact executable prefix used for this pdf2zh_next process."""
    for index, value in enumerate(final_cmd):
        if (
            value == "-m"
            and index + 1 < len(final_cmd)
            and final_cmd[index + 1] == "pdf2zh_next"
        ):
            return final_cmd[: index + 2]
    return final_cmd[:1]


def _python_for_invocation_prefix(invocation_prefix: list[str]) -> Path | None:
    """Resolve the Python interpreter behind a normal pdf2zh_next launcher."""
    if (
        len(invocation_prefix) >= 3
        and invocation_prefix[1] == "-m"
        and invocation_prefix[2] == "pdf2zh_next"
    ):
        candidate = Path(invocation_prefix[0])
        return candidate if candidate.exists() else None

    raw = invocation_prefix[0] if invocation_prefix else ""
    resolved = shutil.which(raw) or raw
    if not resolved:
        return None
    executable = Path(resolved)
    if not executable.exists():
        return None

    names = ["python.exe"] if os.name == "nt" else ["python", "python3"]
    for name in names:
        candidate = executable.parent / name
        if candidate.exists():
            return candidate
    return None


def _runtime_supports_thinking(
    invocation_prefix: list[str],
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> bool:
    isolated = bool(env and env.get("PYTHONNOUSERSITE") == "1")
    cache_key = tuple(
        invocation_prefix
        + ([f"cwd={cwd}"] if cwd else [])
        + [f"isolated={int(isolated)}"]
    )
    if cache_key in _RUNTIME_CAPABILITY_CACHE:
        return _RUNTIME_CAPABILITY_CACHE[cache_key]

    python_path = _python_for_invocation_prefix(invocation_prefix)
    if python_path is not None:
        # Normal uv/conda/system-Python installations can be inspected through
        # their distribution metadata without starting the heavyweight CLI.
        from pdf2zh_server.environment.discovery import (
            runtime_supports_deepseek_thinking,
        )

        supported = runtime_supports_deepseek_thinking(
            python_path,
            env=env,
            isolated=isolated,
        )
    else:
        # Opaque standalone executables (notably the optional Windows bundle)
        # have no inspectable Python environment, so --help remains the only
        # capability signal.  Keep this fallback isolated to that path.
        try:
            result = subprocess.run(
                [*invocation_prefix, "--help"],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                cwd=cwd,
            )
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            supported = (
                result.returncode == 0
                and THINKING_MODE_FLAG in output
                and REASONING_EFFORT_FLAG in output
            )
        except Exception:
            supported = False

    _RUNTIME_CAPABILITY_CACHE[cache_key] = supported
    return supported


def _unsupported_runtime_message(*, winexe: bool = False) -> str:
    if winexe:
        return (
            "当前实际使用的 Windows pdf2zh_next.exe 不支持 DeepSeek V4 思考控制。"
            "为避免 thinking 设置被忽略并产生额外费用，本次翻译已在 API 调用前停止。"
            "请更新到支持 --deepseek-thinking-mode 的新版 exe，或关闭 --enable_winexe "
            "后在 server 目录运行 `python update_packages.py`。"
        )
    return (
        "当前实际使用的 pdf2zh_next 不支持 DeepSeek V4 思考控制。"
        "为避免 thinking 设置被忽略并产生额外费用，本次翻译已在 API 调用前停止。"
        "请在 server 目录运行 `python update_packages.py`，完成后重启 Server。"
    )


def prepare_deepseek_runtime_command(
    final_cmd: list[str],
    final_env: dict[str, str] | None = None,
) -> list[str]:
    """Validate the actual runtime and map config fields to upstream CLI flags.

    pdf2zh_next generates --deepseek-thinking-mode and
    --deepseek-reasoning-effort from the same DeepSeekSettings fields that are
    accepted in config.toml. Passing them explicitly on the CLI makes the
    runtime behavior match the upstream developer-provided command examples and
    prevents an older runtime from silently ignoring config-only fields.
    """
    if "--deepseek" not in final_cmd:
        return final_cmd

    config_path = _option_value(final_cmd, "--config-file")
    if not config_path:
        return final_cmd

    try:
        config_data = toml.load(config_path)
    except Exception as exc:
        raise ValueError(f"无法读取 pdf2zh_next 配置文件: {exc}") from exc

    detail = config_data.get("deepseek_detail", {})
    if not isinstance(detail, dict):
        detail = {}

    model = _option_value(final_cmd, "--deepseek-model") or detail.get(
        "deepseek_model", ""
    )
    if not is_deepseek_thinking_model(model):
        return final_cmd

    mode = resolved_thinking_mode(
        _option_value(final_cmd, THINKING_MODE_FLAG) or detail.get(THINKING_MODE_FIELD)
    )

    effort = _option_value(final_cmd, REASONING_EFFORT_FLAG) or detail.get(
        REASONING_EFFORT_FIELD
    )
    if mode == "enabled":
        effort = str(effort or "high").strip().lower()
        if effort not in DEEPSEEK_EFFORT_VALUES:
            raise ValueError(
                "DeepSeek reasoning effort 仅支持: "
                + "/".join(DEEPSEEK_EFFORT_VALUES)
                + "。"
            )

    invocation_prefix = _invocation_prefix(final_cmd)
    supported = _runtime_supports_thinking(invocation_prefix, env=final_env)
    # deepseek-flash defaults to thinking ON; never strip flags and proceed.
    if is_deepseek_flash_model(model) and not supported:
        raise ValueError(
            "当前 pdf2zh_next 无法验证 deepseek-flash 思考控制。"
            "为避免默认思考导致额外费用，本次在调用 API 前停止。"
            "请使用支持 Python 运行时补丁的 PDF2ZH Next 2.9.0 环境。"
        )
    policy = thinking_runtime_policy(mode, supported)
    if policy == "block":
        raise ValueError(_unsupported_runtime_message())
    if policy == "strip-and-allow":
        strip_thinking_fields_from_config(config_path)
        updated = _remove_option(list(final_cmd), THINKING_MODE_FLAG)
        updated = _remove_option(updated, REASONING_EFFORT_FLAG)
        print(
            "ℹ️ [DeepSeek V4] 当前 pdf2zh_next 不支持思考控制；"
            "本次为不思考，已放行翻译。"
        )
        return updated

    updated = _remove_option(list(final_cmd), THINKING_MODE_FLAG)
    updated = _remove_option(updated, REASONING_EFFORT_FLAG)
    updated.extend([THINKING_MODE_FLAG, mode])
    if mode == "enabled":
        updated.extend([REASONING_EFFORT_FLAG, str(effort)])
    if is_deepseek_flash_model(model):
        updated.append(FLASH_PATCH_FLAG)

    print(
        "🧠 [DeepSeek] 已验证当前 pdf2zh_next 支持思考控制；"
        f"thinking={mode}"
        + (f", reasoning_effort={effort}" if mode == "enabled" else "")
    )
    return updated


def _server_cli_option(name: str, default: str | None = None) -> str | None:
    flag = "--" + name
    for index, value in enumerate(sys.argv[1:], start=1):
        if value == flag and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        prefix = flag + "="
        if value.startswith(prefix):
            return value[len(prefix) :]
    return default


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def validate_winexe_runtime_if_selected(
    config_file: str,
    effective_model: str,
    thinking_mode: Any = "disabled",
) -> bool:
    """Protect the winexe path, which bypasses execute_with_progress().

    Returns True when thinking fields may be written into config.toml.
    Missing/disabled thinking on an old exe is allowed; enabled thinking is not.
    """
    if not is_deepseek_thinking_model(effective_model):
        return False
    if not _as_bool(_server_cli_option("enable_winexe", "false")):
        return True

    configured_path = _server_cli_option(
        "winexe_path",
        "./pdf2zh-v2.6.3-BabelDOC-v0.5.7-win64/pdf2zh/pdf2zh.exe",
    )
    exe_path = Path(str(configured_path))
    # Match server.py exactly: os.path.exists(args.winexe_path) is evaluated
    # relative to the Server process working directory. If it is absent,
    # server.py falls back to the normal venv/system execution path.
    actual_path = exe_path if exe_path.is_absolute() else Path.cwd() / exe_path
    if not actual_path.exists():
        return True
    actual_path = actual_path.resolve()

    if is_deepseek_flash_model(effective_model):
        raise ValueError(
            "Windows 独立 EXE 无法加载 deepseek-flash 的 Python 思考控制补丁。"
            "为避免意外产生思考费用，本次翻译已在 API 调用前停止。"
            "请关闭 --enable_winexe，改用 Server 管理的 Python 环境。"
        )

    supported = _runtime_supports_thinking(
        [str(actual_path)],
        env=os.environ.copy(),
        cwd=str(actual_path.parent),
    )
    policy = thinking_runtime_policy(thinking_mode, supported)
    if policy == "block":
        raise ValueError(_unsupported_runtime_message(winexe=True))
    return policy == "pass-flags"
