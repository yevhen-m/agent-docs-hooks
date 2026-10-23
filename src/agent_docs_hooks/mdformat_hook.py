"""`mdformat`: formats markdown with mdformat and its plugins, and never touches the git index.

Re-staging formatted files would let a single `git commit` pass, but when the formatting conflicts
with unstaged edits that pre-commit stashed, it can lose those edits; see the README.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import mdformat._cli

from agent_docs_hooks._repo import repo_root

DEFAULT_OPTIONS = (
    "--wrap",
    "100",
    "--number",
    "--end-of-line",
    "lf",
    "--extensions",
    "frontmatter",
    "--extensions",
    "gfm",
)
ROOT_CONFIG = ".mdformat.toml"
NOT_UTF8 = "isn't saved as UTF-8, so mdformat can't read it; save it as UTF-8"


def format_args(*, has_root_config: bool, paths: Sequence[str]) -> list[str]:
    """mdformat's arguments: the default options unless the repo root has its own config."""
    options = [] if has_root_config else list(DEFAULT_OPTIONS)
    return [*options, "--", *paths]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-docs-mdformat",
        description="Format markdown files in place. Prints each file it changed.",
    )
    parser.add_argument("paths", nargs="*", metavar="PATH")
    paths: list[str] = parser.parse_args(argv).paths
    if not paths:
        return 0

    has_root_config = (repo_root() / ROOT_CONFIG).is_file()
    before = {path: _contents(path) for path in paths}
    unreadable = [path for path, data in before.items() if not _is_utf8(data)]
    sys.stdout.write("".join(f"{path}: {NOT_UTF8}\n" for path in unreadable))
    readable = [path for path in paths if path not in unreadable]
    status = 0
    try:
        if readable:
            status = mdformat._cli.run(format_args(has_root_config=has_root_config, paths=readable))
    finally:
        changed = [path for path in readable if _contents(path) != before[path]]
        sys.stdout.write("".join(f"{path}: reformatted\n" for path in changed))
    return 1 if unreadable or changed or status != 0 else 0


def _contents(path: str) -> bytes | None:
    file = Path(path)
    return file.read_bytes() if file.is_file() else None


def _is_utf8(data: bytes | None) -> bool:
    """mdformat decodes each file as strict UTF-8 and raises mid-batch on the first that isn't."""
    if data is None:
        return True
    try:
        data.decode()
    except UnicodeDecodeError:
        return False
    return True
