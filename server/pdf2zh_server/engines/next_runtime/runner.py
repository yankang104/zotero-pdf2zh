"""Run the installed pdf2zh_next engine with optional runtime policies."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def main():
    from importlib.metadata import distribution

    from pdf2zh_server.engines.next_runtime.launcher import REFERENCE_FLAG
    from pdf2zh_server.engines.next_runtime.process_policy import (
        install_table_process_policy,
    )
    from pdf2zh_server.pdf.reference_skip import policy_supported, warn_native_fallback
    from pdf2zh_server.pdf.tables.mode import parse_table_mode
    from pdf2zh_server.pdf.tables.runtime import (
        table_policy_supported,
        warn_native_table_fallback,
    )
    from pdf2zh_server.providers.deepseek_options import FLASH_PATCH_FLAG
    from pdf2zh_server.providers.relay_patch import RELAY_PATCH_FLAG

    mode = sys.argv.pop(1)
    mode = None if mode == "none" else parse_table_mode(mode)
    reference_skip = len(sys.argv) > 1 and sys.argv[1] == REFERENCE_FLAG
    if reference_skip:
        sys.argv.pop(1)
    flash_patch = len(sys.argv) > 1 and sys.argv[1] == FLASH_PATCH_FLAG
    if flash_patch:
        sys.argv.pop(1)
    relay_patch = None
    if len(sys.argv) > 2 and sys.argv[1] == RELAY_PATCH_FLAG:
        sys.argv.pop(1)
        relay_patch = sys.argv.pop(1)
    if mode and not table_policy_supported():
        warn_native_table_fallback()
        # Restore native table OCR for an unverified upstream version.
        if "--translate-table-text" not in sys.argv:
            sys.argv.append("--translate-table-text")
        mode = None
    if reference_skip and not policy_supported():
        warn_native_fallback()
        reference_skip = False
    restores = []
    try:
        # The parent handles debug/in-process translation. The composed
        # process policy also reinstalls hooks in fork/spawn child workers.
        if mode or reference_skip or flash_patch or relay_patch:
            restores.append(
                install_table_process_policy(
                    mode,
                    reference_skip=reference_skip,
                    flash_patch=flash_patch,
                    **({"relay_patch": relay_patch} if relay_patch else {}),
                )
            )
        entry = next(
            entry
            for entry in distribution("pdf2zh-next").entry_points
            if entry.group == "console_scripts" and entry.name == "pdf2zh_next"
        )
        sys.argv[0] = "pdf2zh_next"
        return entry.load()()
    finally:
        for restore in reversed(restores):
            restore()


if __name__ == "__main__":
    sys.exit(main())
