from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
from collections.abc import Mapping
from pathlib import Path

from pdf2zh_server.paths import SERVER_ROOT


def _configure_windows_console_output() -> None:
    """Prevent diagnostic Unicode from crashing legacy Windows consoles.

    Keep the console's chosen encoding (for example GBK/CP936) and only make
    unrepresentable characters replaceable. This avoids UnicodeEncodeError
    from status symbols such as check marks without forcing UTF-8 on users.
    """
    if platform.system() != "Windows":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(errors="replace")
        except (OSError, ValueError, TypeError):
            pass


_configure_windows_console_output()


DEFAULT_VENV_CONFIG = SERVER_ROOT / "config" / "venv.json.example"


ENGINE_ENV_NAMES = {
    "pdf2zh_next": "zotero-pdf2zh-next-venv",
    "wenyi": "zotero-wenyi-venv",
}


PRIMARY_PACKAGES = {
    "pdf2zh_next": "pdf2zh-next",
    "wenyi": "wenyi-cli",
}


VERSION_PACKAGES = {
    "pdf2zh_next": ["pdf2zh-next", "BabelDOC", "PyMuPDF", "pypdf", "bitstring"],
    "wenyi": ["wenyi-cli", "wenyi-core", "wenyi-babeldoc-bridge", "BabelDOC", "PyMuPDF"],
}


THINKING_FLAGS = (
    "--deepseek-thinking-mode",
    "--deepseek-reasoning-effort",
)


MIN_PDF2ZH_NEXT = (2, 9, 0)


def managed_python_env(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return an environment isolated from ambient Python package paths.

    Managed uv/conda runtimes must resolve packages from their own prefix. A
    machine-wide PYTHONPATH or PYTHONHOME can otherwise make a venv CLI import
    pure-Python files from the system installation while loading compiled
    extensions from somewhere else. Keep every unrelated variable (PATH,
    proxies, CUDA settings, credentials, and terminal settings) unchanged.
    """
    env = dict(os.environ if source is None else source)
    blocked = {"PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE"}
    for key in tuple(env):
        if key.upper() in blocked:
            env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _version_tuple(value: str | None) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(value or ""))
    return tuple(int(part) for part in parts[:4]) or (0,)


def pdf2zh_next_meets_minimum(version: str | None) -> bool:
    """Return True when the installed pdf2zh-next already satisfies 2.9.0."""
    if not version or str(version).strip().lower() in {"unknown", "none"}:
        return False
    return _version_tuple(version) >= MIN_PDF2ZH_NEXT


def environment_python_candidates(env_dir: Path) -> tuple[Path, ...]:
    """Return supported Python locations for a managed environment.

    On Windows, uv/venv puts Python in ``Scripts\\python.exe`` while Conda
    puts it at the environment root as ``<env>\\python.exe``.  The v4.1.0
    lifecycle originally assumed the uv layout for both managers, which made a
    healthy Windows Conda environment look broken immediately after creation.
    """
    env_dir = Path(env_dir)
    if platform.system() == "Windows":
        return (
            env_dir / "python.exe",
            env_dir / "python3.exe",
            env_dir / "Scripts" / "python.exe",
            env_dir / "Scripts" / "python3.exe",
        )
    return (env_dir / "bin" / "python", env_dir / "bin" / "python3")


def resolve_environment_python(env_dir: Path) -> Path:
    candidates = environment_python_candidates(env_dir)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Callers still verify existence.  This fallback only gives diagnostics a
    # manager-appropriate expected path when environment creation is incomplete.
    env_dir = Path(env_dir)
    if platform.system() == "Windows" and (env_dir / "conda-meta").exists():
        return env_dir / "python.exe"
    return candidates[-1]


def resolve_environment_root(python_path: Path) -> Path:
    """Recover an environment root from either uv/venv or Conda Python."""
    python_path = Path(python_path)
    parent = python_path.parent
    if platform.system() == "Windows":
        return parent.parent if parent.name.lower() == "scripts" else parent
    return parent.parent if parent.name == "bin" else parent


def environment_path_entries(env_dir: Path, env_tool: str) -> list[Path]:
    """Return PATH entries needed to execute tools from a managed environment."""
    env_dir = Path(env_dir)
    if platform.system() != "Windows":
        candidates = [env_dir / "bin"]
    elif env_tool == "conda":
        # Important parts of a normal ``conda activate`` PATH on Windows.
        candidates = [
            env_dir,
            env_dir / "Library" / "mingw-w64" / "bin",
            env_dir / "Library" / "usr" / "bin",
            env_dir / "Library" / "bin",
            env_dir / "Scripts",
            env_dir / "bin",
        ]
    else:
        candidates = [env_dir / "Scripts"]

    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(str(candidate)))
        if candidate.exists() and key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _python_in_env_dir(env_dir: Path) -> Path:
    # Compatibility alias for the lifecycle internals.
    return resolve_environment_python(env_dir)


def _bin_dir(env_dir: Path) -> Path:
    return env_dir / ("Scripts" if platform.system() == "Windows" else "bin")


def load_environment_config(config_path: str | os.PathLike[str] | None = None) -> dict:
    path = Path(config_path) if config_path else DEFAULT_VENV_CONFIG
    if not path.exists():
        path = DEFAULT_VENV_CONFIG
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_requirements(
    engine: str,
    env_tool: str,
    config_path: str | os.PathLike[str] | None = None,
) -> tuple[str, list[str]]:
    config = load_environment_config(config_path)
    engine_config = config.get(engine, {}).get(env_tool, {})
    packages = list(engine_config.get("packages", []))
    if engine == "pdf2zh_next" and packages and "bitstring>=4.3.0,<5" not in packages:
        packages.append("bitstring>=4.3.0,<5")
    return (
        str(engine_config.get("python_version", "3.12")),
        packages,
    )


def _conda_info() -> dict | None:
    if not shutil.which("conda"):
        return None
    try:
        result = subprocess.run(
            ["conda", "info", "--json"],
            capture_output=True,
            text=True,
            check=True,
            env=managed_python_env(),
            timeout=60,
        )
        return json.loads(result.stdout)
    except Exception:
        return None


def find_conda_env_path(name: str) -> Path | None:
    info = _conda_info()
    if not info:
        return None
    for raw_path in info.get("envs", []):
        path = Path(raw_path)
        if path.name == name:
            return path
    for raw_dir in info.get("envs_dirs", []):
        path = Path(raw_dir) / name
        if path.exists():
            return path
    return None


def _query_conda_python(name: str) -> Path | None:
    """Ask conda which Python a named environment actually runs.

    Windows Conda layouts vary, and ``conda info --json`` can lag behind a
    freshly created environment. ``conda run -n ... python`` is the same
    lookup users get after ``conda activate``.
    """
    conda_path = shutil.which("conda")
    if not conda_path:
        return None
    command = [
        conda_path,
        "run",
        "-n",
        name,
        "python",
        "-c",
        "import sys; print(sys.executable)",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=managed_python_env(),
            timeout=180,
        )
    except Exception:
        return None
    for line in reversed((result.stdout or "").splitlines()):
        candidate = Path(line.strip().strip('"'))
        if candidate.is_file():
            return candidate
    return None


def _resolve_named_conda_python(name: str, env_dir: Path | None = None) -> Path | None:
    env_dir = env_dir or find_conda_env_path(name)
    if env_dir:
        python_path = resolve_environment_python(env_dir)
        if python_path.exists():
            return python_path
    queried = _query_conda_python(name)
    if queried is not None and queried.exists():
        return queried
    return None


def find_existing_environment(
    engine: str,
    env_tool: str = "auto",
) -> tuple[str, Path, Path] | None:
    env_name = ENGINE_ENV_NAMES[engine]
    if env_tool in {"auto", "uv"}:
        env_dir = SERVER_ROOT / env_name
        python_path = _python_in_env_dir(env_dir)
        if python_path.exists():
            return "uv", env_dir, python_path
    if env_tool in {"auto", "conda"}:
        env_dir = find_conda_env_path(env_name)
        python_path = _resolve_named_conda_python(env_name, env_dir)
        if python_path is not None and python_path.exists():
            return "conda", resolve_environment_root(python_path), python_path
    return None


def read_versions(python_path: Path, engine: str) -> dict[str, str | None]:
    names = VERSION_PACKAGES[engine]
    code = (
        "import json; "
        "from importlib.metadata import version, PackageNotFoundError; "
        f"names={names!r}; out={{}}; "
        "\nfor name in names:\n"
        "    try: out[name]=version(name)\n"
        "    except PackageNotFoundError: out[name]=None\n"
        "print(json.dumps(out))"
    )
    result = subprocess.run(
        [str(python_path), "-I", "-c", code],
        capture_output=True,
        text=True,
        env=managed_python_env(),
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "无法读取翻译环境版本")
    return json.loads(result.stdout)


def format_versions(versions: dict[str, str | None]) -> str:
    return ", ".join(
        f"{name}={value}" for name, value in versions.items() if value is not None
    )


def resolve_unmanaged_pdf2zh_command(command: list[str]) -> list[str]:
    """Prefer PATH, then the launcher in the Server Python's scripts directory."""
    executable = shutil.which(command[0])
    if executable is None:
        script_name = (
            "pdf2zh_next.exe" if platform.system() == "Windows" else "pdf2zh_next"
        )
        launcher = Path(sysconfig.get_path("scripts")) / script_name
        if not launcher.is_file():
            raise RuntimeError(
                "当前未启用托管环境，PATH 和当前 Server Python 的脚本目录均未找到 "
                f"pdf2zh_next。当前 Python：{sys.executable}。"
                "请使用已安装引擎的 Python 启动 Server，或先激活对应环境。"
            )
        executable = str(launcher)
    return [str(Path(executable).absolute()), *command[1:]]


def _runtime_command(python_path: Path, module: str) -> list[str]:
    env_dir = resolve_environment_root(python_path)
    executable = _bin_dir(env_dir) / (
        module + (".exe" if platform.system() == "Windows" else "")
    )
    if executable.exists():
        return [str(executable)]
    return [str(python_path), "-m", module]


def runtime_supports_deepseek_thinking(
    python_path: Path,
    *,
    env: Mapping[str, str] | None = None,
    isolated: bool = False,
) -> bool:
    """Check DeepSeek V4 capability without importing or starting pdf2zh_next.

    pdf2zh_next 2.9.0 imports BabelDOC/high-level modules before its CLI parser
    runs, so ``pdf2zh_next --help`` is not a safe health probe: on some Macs it
    can spend more than a minute in import/asset initialization.  We instead
    inspect the installed distribution files using importlib.metadata from the
    target interpreter.  This verifies both DeepSeek setting fields and the
    generic underscore-to-hyphen CLI argument generation used upstream.
    """
    code = (
        "import json; "
        "from importlib.metadata import distribution; "
        "from pathlib import Path; "
        "out={'supported': False, 'reason': ''}; "
        "\ntry:\n"
        "    dist=distribution('pdf2zh-next')\n"
        "    settings=Path(dist.locate_file('pdf2zh_next/config/translate_engine_model.py'))\n"
        "    cli=Path(dist.locate_file('pdf2zh_next/config/main.py'))\n"
        "    settings_text=settings.read_text(encoding='utf-8')\n"
        "    cli_text=cli.read_text(encoding='utf-8')\n"
        "    fields=('deepseek_thinking_mode','deepseek_reasoning_effort')\n"
        "    field_ok=all(field in settings_text for field in fields)\n"
        '    cli_ok=\'field_name.replace("_", "-").lower()\' in cli_text\n'
        "    out={'supported': bool(field_ok and cli_ok), 'reason': 'ok' if field_ok and cli_ok else 'missing-fields-or-cli-mapping'}\n"
        "except Exception as exc:\n"
        "    out={'supported': False, 'reason': type(exc).__name__ + ': ' + str(exc)}\n"
        "print(json.dumps(out))"
    )
    try:
        runtime_env = (
            managed_python_env(env)
            if isolated
            else dict(os.environ if env is None else env)
        )
        command = [str(python_path)]
        if isolated:
            command.append("-I")
        command.extend(["-c", code])
        result = subprocess.run(
            command,
            cwd=SERVER_ROOT,
            capture_output=True,
            text=True,
            env=runtime_env,
            timeout=20,
        )
        if result.returncode != 0:
            return False
        payload = json.loads(result.stdout.strip() or "{}")
        return bool(payload.get("supported"))
    except Exception:
        return False
