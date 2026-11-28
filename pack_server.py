#!/usr/bin/env python3
"""Package current Server sources into the repository's server.zip.

Usage:
    python pack_server.py [--output server.zip] [--include-tests]

Package the application, command entry points, runtime assets and example
configuration. Existing user data and unrelated folders are outside this list.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent


def server_source_files() -> list[str]:
    server = REPO / "server"
    files = [
        server / name
        for name in (
            "server.py", "manage_packages.py", "update_packages.py",
            "requirements.txt", "notice.json", "config.yaml",
        )
    ]
    files.extend((server / "config").glob("*.example"))
    for directory in ("pdf2zh_server", "warmup"):
        files.extend(
            path for path in (server / directory).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in (".pyc", ".pyo")
        )
    return sorted(path.relative_to(REPO).as_posix() for path in files)


def build(output: Path, include_tests: bool) -> None:
    files = server_source_files()
    if include_tests:
        files.extend(
            path.relative_to(REPO).as_posix()
            for path in (REPO / "server" / "tests").rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in (".pyc", ".pyo")
        )

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in files:
            archive.write(REPO / source, source)

    print(f"{output.name}: packaged {len(files)} files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("server.zip"), help="输出路径"
    )
    parser.add_argument(
        "--include-tests", action="store_true", help="把 server/tests 打进包"
    )
    args = parser.parse_args()
    build(REPO / args.output, args.include_tests)


if __name__ == "__main__":
    main()
