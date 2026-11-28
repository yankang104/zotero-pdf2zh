from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from pdf2zh_server.environment.discovery import (
    ENGINE_ENV_NAMES,
    PRIMARY_PACKAGES,
    _bin_dir,
    _resolve_named_conda_python,
    find_conda_env_path,
    find_existing_environment,
    format_versions,
    load_requirements,
    managed_python_env,
    read_versions,
    resolve_environment_python,
    resolve_environment_root,
    runtime_supports_deepseek_thinking,
)
from pdf2zh_server.environment.network import (
    print_probe_report,
    probe_indexes,
    usable_indexes,
)
from pdf2zh_server.paths import SERVER_ROOT


def _package_manager_env() -> dict[str, str]:
    env = managed_python_env()
    env.setdefault("UV_HTTP_CONNECT_TIMEOUT", "10")
    env.setdefault("UV_HTTP_TIMEOUT", "120")
    env.setdefault("UV_HTTP_RETRIES", "5")
    return env


def _pip_supports_dry_run(python_path: Path) -> bool:
    try:
        result = subprocess.run(
            [str(python_path), "-I", "-m", "pip", "install", "--help"],
            capture_output=True,
            text=True,
            env=managed_python_env(),
            timeout=30,
        )
        return result.returncode == 0 and "--dry-run" in (result.stdout or "")
    except Exception:
        return False


def _build_install_command(
    env_tool: str,
    python_path: Path,
    requirements: Iterable[str],
    index_url: str,
    *,
    dry_run: bool,
    reinstall: bool = False,
    upgrade: bool = False,
) -> list[str] | None:
    requirements = list(requirements)
    if env_tool == "uv":
        uv_path = shutil.which("uv")
        if not uv_path:
            return None
        command = [uv_path, "pip", "install"]
        if upgrade:
            command.append("--upgrade")
        if dry_run:
            command.append("--dry-run")
        elif reinstall:
            command.append("--reinstall")
        command.extend(
            ["--index-url", index_url, *requirements, "--python", str(python_path)]
        )
        return command
    if dry_run and not _pip_supports_dry_run(python_path):
        return None
    command = [str(python_path), "-I", "-m", "pip", "install"]
    if upgrade:
        command.append("--upgrade")
    if dry_run:
        command.append("--dry-run")
    elif reinstall:
        command.append("--force-reinstall")
    command.extend(["--index-url", index_url, *requirements])
    return command


def _resolver_preflight(
    env_tool: str,
    python_path: Path,
    requirements: list[str],
    index_url: str,
    *,
    upgrade: bool = False,
) -> bool:
    command = _build_install_command(
        env_tool, python_path, requirements, index_url, dry_run=True, upgrade=upgrade
    )
    if command is None:
        return env_tool == "conda"
    try:
        result = subprocess.run(
            command,
            cwd=SERVER_ROOT,
            capture_output=True,
            text=True,
            env=_package_manager_env(),
            timeout=180,
        )
        return result.returncode == 0
    except Exception:
        return False


def choose_install_sources(
    engine: str,
    env_tool: str,
    python_path: Path,
    requirements: list[str],
    preferred_index: str | None = None,
    network_timeout: float = 4.0,
    upgrade: bool = False,
) -> list[str]:
    results = probe_indexes(
        PRIMARY_PACKAGES[engine],
        preferred_index=preferred_index,
        timeout=network_timeout,
    )
    print_probe_report(results)
    sources: list[str] = []
    for result in usable_indexes(results):
        if _resolver_preflight(
            env_tool, python_path, requirements, result.url, upgrade=upgrade
        ):
            sources.append(result.url)
    return sources


def _remove_conda_env(name: str) -> None:
    if not shutil.which("conda") or not find_conda_env_path(name):
        return
    try:
        subprocess.run(
            ["conda", "env", "remove", "-n", name, "-y"],
            cwd=SERVER_ROOT,
            check=False,
            env=managed_python_env(),
            timeout=1200,
        )
    except Exception:
        pass


def _create_uv_environment(path: Path, python_version: str) -> Path:
    uv_path = shutil.which("uv")
    if not uv_path:
        raise RuntimeError("未找到 uv")
    existing = resolve_environment_python(path)
    if existing.exists():
        return existing
    shutil.rmtree(path, ignore_errors=True)
    subprocess.run(
        [uv_path, "venv", str(path), "--python", python_version],
        cwd=SERVER_ROOT,
        check=True,
        env=_package_manager_env(),
        timeout=1200,
    )
    python_path = resolve_environment_python(path)
    if not python_path.exists():
        raise RuntimeError(f"uv 环境没有生成 Python 可执行文件: {path}")
    return python_path


def _create_conda_environment(name: str, python_version: str) -> tuple[Path, Path]:
    conda_path = shutil.which("conda")
    if not conda_path:
        raise RuntimeError("未找到 conda")
    python_path = _resolve_named_conda_python(name)
    if python_path is not None:
        return resolve_environment_root(python_path), python_path
    subprocess.run(
        [
            conda_path,
            "create",
            "-n",
            name,
            f"python={python_version}",
            "pip",
            "-y",
        ],
        cwd=SERVER_ROOT,
        check=True,
        env=managed_python_env(),
        timeout=1200,
    )
    python_path = _resolve_named_conda_python(name)
    if python_path is None or not python_path.exists():
        raise RuntimeError(
            f"conda 环境 {name} 创建后仍找不到 Python 可执行文件。"
            "请在终端执行 `conda activate "
            + name
            + "` 后运行 `where python`（Windows）"
            "或 `which python` 确认环境是否可用。"
        )
    return resolve_environment_root(python_path), python_path


def _cleanup_legacy_sidecar_environments(engine: str, env_tool: str) -> None:
    env_name = ENGINE_ENV_NAMES[engine]
    if env_tool == "uv":
        shutil.rmtree(SERVER_ROOT / f"{env_name}.staging", ignore_errors=True)
        shutil.rmtree(SERVER_ROOT / f"{env_name}.backup", ignore_errors=True)
        return
    _remove_conda_env(f"{env_name}-staging")
    _remove_conda_env(f"{env_name}-backup")


def _ensure_canonical_environment(
    engine: str,
    env_tool: str,
    python_version: str,
) -> tuple[Path, Path]:
    env_name = ENGINE_ENV_NAMES[engine]
    if env_tool == "uv":
        env_dir = SERVER_ROOT / env_name
        python_path = _create_uv_environment(env_dir, python_version)
        return env_dir, python_path
    return _create_conda_environment(env_name, python_version)


def _run_install(
    env_tool: str,
    python_path: Path,
    requirements: list[str],
    sources: list[str],
    *,
    reinstall: bool = False,
    upgrade: bool = False,
) -> bool:
    for position, index_url in enumerate(sources, start=1):
        command = _build_install_command(
            env_tool,
            python_path,
            requirements,
            index_url,
            dry_run=False,
            reinstall=reinstall,
            upgrade=upgrade,
        )
        if command is None:
            return False
        print(f"\n📦 使用下载源: {index_url}")
        try:
            subprocess.run(
                command,
                cwd=SERVER_ROOT,
                check=True,
                env=_package_manager_env(),
                timeout=1200,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            print(f"❌ 安装失败: {exc}")
            if position < len(sources):
                print("↪ 自动切换到下一已验证下载源。")
    return False


def managed_runtime_health(
    engine: str,
    python_path: Path,
) -> tuple[bool, str]:
    """Check Next's native dependencies; Wenyi depends on package validation."""
    if engine == "wenyi":
        return True, "ok"

    modules = ["pydantic", "pydantic_core", "pydantic_core._pydantic_core", "bitstring"]
    code = (
        "import importlib, json, os, sys; "
        "root=os.path.normcase(os.path.realpath(sys.prefix)); "
        f"names={modules!r}; "
        "out={'ok': True, 'reason': 'ok', 'root': root}; "
        "\ntry:\n"
        "    for name in names:\n"
        "        module=importlib.import_module(name)\n"
        "        origin=getattr(module, '__file__', None)\n"
        "        if not origin:\n"
        "            raise RuntimeError(name + ' 没有可验证的文件路径')\n"
        "        origin=os.path.normcase(os.path.realpath(origin))\n"
        "        try:\n"
        "            inside=os.path.commonpath((root, origin)) == root\n"
        "        except ValueError:\n"
        "            inside=False\n"
        "        if not inside:\n"
        "            raise RuntimeError(name + ' 来自托管环境之外: ' + origin)\n"
        "    from bitstring import BitStream\n"
        "    BitStream()\n"
        "except Exception as exc:\n"
        "    out={'ok': False, 'reason': type(exc).__name__ + ': ' + str(exc), 'root': root}\n"
        "print(json.dumps(out, ensure_ascii=False))"
    )
    try:
        result = subprocess.run(
            [str(python_path), "-I", "-c", code],
            cwd=SERVER_ROOT,
            capture_output=True,
            text=True,
            env=managed_python_env(),
            timeout=30,
        )
        if result.returncode != 0:
            reason = (result.stderr or result.stdout or "unknown error").strip()
            return False, reason
        payload = json.loads(result.stdout.strip() or "{}")
        return bool(payload.get("ok")), str(payload.get("reason") or "unknown error")
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def validate_environment(
    engine: str,
    python_path: Path,
    requirements: list[str],
    *,
    require_deepseek_thinking: bool = False,
) -> bool:
    try:
        code = (
            "from packaging.requirements import Requirement; "
            "from importlib.metadata import version; "
            f"reqs={requirements!r}; "
            "\nfor raw in reqs:\n"
            "    req=Requirement(raw)\n"
            "    installed=version(req.name)\n"
            "    assert not req.specifier or req.specifier.contains(installed), (raw, installed)\n"
        )
        result = subprocess.run(
            [str(python_path), "-I", "-c", code],
            cwd=SERVER_ROOT,
            capture_output=True,
            text=True,
            env=managed_python_env(),
            timeout=90,
        )
        if result.returncode != 0:
            print(
                "❌ 环境依赖完整性检查失败:", (result.stderr or result.stdout).strip()
            )
            return False
        if engine == "wenyi":
            return True
        healthy, reason = managed_runtime_health(engine, python_path)
        if not healthy:
            print(f"❌ {engine} 关键运行时依赖检查失败: {reason}")
            return False
        module = "pdf2zh_next"
        env_dir = resolve_environment_root(python_path)
        suffix = ".exe" if platform.system() == "Windows" else ""
        cli_name = module + suffix
        executable = next(
            (
                candidate
                for candidate in (
                    _bin_dir(env_dir) / cli_name,
                    env_dir / cli_name,
                )
                if candidate.exists()
            ),
            None,
        )
        if executable is None:
            print(f"❌ {module} CLI 入口不存在: {_bin_dir(env_dir) / cli_name}")
            return False

        # Do not launch the heavyweight pdf2zh_next CLI help path here. Upstream imports
        # BabelDOC/high-level modules before CLI parsing, so --help can be a
        # heavyweight operation and is not a reliable installation probe.
        if require_deepseek_thinking and engine == "pdf2zh_next":
            if not runtime_supports_deepseek_thinking(
                python_path,
                env=managed_python_env(),
                isolated=True,
            ):
                print("❌ pdf2zh_next 缺少 DeepSeek V4 thinking capability")
                return False
        return True
    except Exception as exc:
        print(f"❌ 环境验证失败: {exc}")
        return False


def transactional_install_or_update(
    engine: str = "pdf2zh_next",
    *,
    env_tool: str = "auto",
    config_path: str | os.PathLike[str] | None = None,
    preferred_index: str | None = None,
    network_timeout: float = 4.0,
    require_deepseek_thinking: bool = False,
    force_reinstall: bool = False,
) -> tuple[bool, str | None, Path | None]:
    if engine not in ENGINE_ENV_NAMES:
        raise ValueError(f"Unknown engine: {engine}")
    existing = find_existing_environment(engine, env_tool)
    selected_tool = existing[0] if existing else None
    if selected_tool is None:
        candidates = [env_tool] if env_tool in {"uv", "conda"} else ["uv", "conda"]
        selected_tool = next((tool for tool in candidates if shutil.which(tool)), None)
    if selected_tool is None:
        print("❌ 未找到可用的 uv 或 conda，无法创建翻译环境。")
        return False, None, None
    python_version, requirements = load_requirements(engine, selected_tool, config_path)
    if not requirements:
        print(f"❌ {engine} 没有声明安装依赖。")
        return False, selected_tool, existing[1] if existing else None
    try:
        _cleanup_legacy_sidecar_environments(engine, selected_tool)
        print(
            "\n📦 将在当前翻译环境中直接安装/更新依赖，不再创建 staging 或 backup 环境。"
        )
        if existing:
            env_dir, python_path = existing[1], existing[2]
            print(f"   使用已有 {selected_tool} 环境: {env_dir}")
            print(f"   Python: {python_path}")
        else:
            print(f"   正在创建 {selected_tool} 环境: {ENGINE_ENV_NAMES[engine]}")
            env_dir, python_path = _ensure_canonical_environment(
                engine, selected_tool, python_version
            )
            print(f"   Python: {python_path}")
        if not python_path.exists():
            print(f"❌ 找不到 Python 可执行文件: {python_path}")
            return False, selected_tool, env_dir
        if existing and not force_reinstall and engine != "wenyi":
            healthy, reason = managed_runtime_health(engine, python_path)
            if not healthy:
                force_reinstall = True
                print(f"🔧 检测到 {engine} 关键依赖损坏，将重新安装完整依赖: {reason}")
        before_versions = None
        try:
            before_versions = read_versions(python_path, engine)
        except Exception:
            pass
        sources = choose_install_sources(
            engine,
            selected_tool,
            python_path,
            requirements,
            preferred_index=preferred_index,
            network_timeout=network_timeout,
            upgrade=(engine == "wenyi"),
        )
        if not sources:
            print("❌ 没有可验证且能解析完整依赖的下载源。")
            return False, selected_tool, env_dir
        if not _run_install(
            selected_tool,
            python_path,
            requirements,
            sources,
            reinstall=force_reinstall,
            upgrade=(engine == "wenyi"),
        ):
            return False, selected_tool, env_dir
        if not validate_environment(
            engine,
            python_path,
            requirements,
            require_deepseek_thinking=require_deepseek_thinking,
        ):
            return False, selected_tool, env_dir
        after_versions = read_versions(python_path, engine)
        print("\n✅ 翻译环境已更新。")
        if before_versions:
            print("   更新前:", format_versions(before_versions))
        print("   当前:", format_versions(after_versions))
        return True, selected_tool, env_dir
    except Exception as exc:
        print(f"\n⚠️ 翻译环境安装/更新失败: {exc}")
        restored = find_existing_environment(engine, selected_tool)
        if restored:
            print(
                "   仍将尝试使用当前翻译环境。如果翻译异常，请重新运行 python update_packages.py。"
            )
        else:
            print("   当前没有可用翻译环境；可以稍后重新尝试。")
        return False, selected_tool, restored[1] if restored else None
