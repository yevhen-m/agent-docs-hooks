"""`doc-links`: every relative link and heading anchor in tracked markdown resolves, offline."""

from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from agent_docs_hooks._repo import repo_root, tracked_files

_BINARY_NAMES = ("lychee", "lychee.exe")


def lychee_path() -> Path:
    """The `lychee` binary installed with the `lychee-bin` package, found from the package's own
    file record, so a different `lychee` on `PATH` is never used; exits 2 if it's missing."""
    try:
        distribution = importlib.metadata.distribution("lychee-bin")
    except importlib.metadata.PackageNotFoundError:
        _binary_missing()
    for file in distribution.files or []:
        if file.name in _BINARY_NAMES:
            path = Path(str(distribution.locate_file(file)))
            if path.is_file():
                return path
    _binary_missing()


def _binary_missing() -> NoReturn:
    sys.stderr.write("lychee binary not found; reinstall the hook environment (pre-commit clean)\n")
    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-docs-links",
        description="Check every relative link and heading anchor in tracked markdown, offline.",
    )
    parser.parse_args(argv)

    root = repo_root()
    paths = sorted(path for path in tracked_files(root) if path.endswith(".md"))
    if not paths:
        return 0
    command = [
        str(lychee_path()),
        "--offline",
        "--include-fragments",
        "--no-progress",
        "--root-dir",
        str(root),
        "--",
        *paths,
    ]
    return subprocess.run(command, cwd=root, check=False).returncode
