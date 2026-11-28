import shutil
from pathlib import Path

from pdf2zh_server.pdf.tables.mode import parse_table_mode
from pdf2zh_server.providers.deepseek_options import FLASH_PATCH_FLAG
from pdf2zh_server.providers.relay_patch import RELAY_PATCH_FLAG

FLAG = "--zotero-table-mode"


REFERENCE_FLAG = "--zotero-reference-skip"


def prepare_table_runtime_command(command):
    if (
        FLAG not in command
        and REFERENCE_FLAG not in command
        and FLASH_PATCH_FLAG not in command
        and RELAY_PATCH_FLAG not in command
    ):
        return command
    args = list(command)
    reference_skip = REFERENCE_FLAG in args
    if reference_skip:
        args.remove(REFERENCE_FLAG)
    flash_patch = FLASH_PATCH_FLAG in args
    if flash_patch:
        args.remove(FLASH_PATCH_FLAG)
    relay_patch = None
    if RELAY_PATCH_FLAG in args:
        index = args.index(RELAY_PATCH_FLAG)
        if index + 1 >= len(args):
            raise ValueError("Missing relay options file")
        relay_patch = args[index + 1]
        del args[index : index + 2]
    mode = None
    if FLAG in args:
        index = args.index(FLAG)
        if index + 1 >= len(args):
            raise ValueError("Missing table mode")
        mode = parse_table_mode(args[index + 1])
        del args[index : index + 2]
    if not mode and not reference_skip and not flash_patch and not relay_patch:
        return args
    if not args:
        raise ValueError("Missing engine command")

    executable = Path(shutil.which(args[0]) or args[0])
    if executable.stem.lower() in ("python", "python3", "python3.12", "python3.11"):
        module_index = args.index("-m") if "-m" in args else -1
        if (
            module_index < 0
            or module_index + 1 >= len(args)
            or args[module_index + 1] != "pdf2zh_next"
        ):
            raise ValueError("Table modes require a pdf2zh_next Python invocation")
        engine_args = args[module_index + 2 :]
        python = executable
    else:
        if executable.stem.lower() != "pdf2zh_next":
            raise ValueError("Table modes require the pdf2zh_next Python engine")
        candidates = (
            executable.parent / "python.exe",
            executable.parent.parent / "python.exe",
            executable.parent / "python",
        )
        python = next((p for p in candidates if p.is_file()), None)
        if python is None:
            raise ValueError("Cannot locate the Python interpreter beside pdf2zh_next")
        engine_args = args[1:]
    runner = (
        Path(__file__).resolve().parents[2] / "engines" / "next_runtime" / "runner.py"
    )
    return [
        str(python),
        "-u",
        str(runner),
        mode or "none",
        *([REFERENCE_FLAG] if reference_skip else []),
        *([FLASH_PATCH_FLAG] if flash_patch else []),
        *([RELAY_PATCH_FLAG, relay_patch] if relay_patch else []),
        *engine_args,
    ]
