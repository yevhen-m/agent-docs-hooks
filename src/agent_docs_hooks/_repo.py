"""The effects every hook shares: finding the repo, listing what git tracks, reading, reporting."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from agent_docs_hooks.problems import Problem, RepoPath, render

_REGULAR_FILE_MODES = frozenset({"100644", "100755"})


def repo_root() -> Path:
    """The top of the git work tree holding the current directory; exits 2 outside one."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(2)
    return Path(result.stdout.rstrip("\n"))


def tracked_files(root: Path) -> frozenset[RepoPath]:
    """Tracked regular files present in the working tree; symlinks and submodules are left out."""
    listing = subprocess.run(
        ["git", "ls-files", "--stage", "-z"], cwd=root, capture_output=True, check=True
    ).stdout
    paths = set()
    for entry in os.fsdecode(listing).split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        mode = meta.split(" ", 1)[0]
        if mode in _REGULAR_FILE_MODES and _is_regular_file(root / path):
            paths.add(RepoPath(path))
    return frozenset(paths)


def _is_regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def normalize_root(value: str) -> str:
    """argparse `type=` for path options: a clean repo-relative path, or a usage error."""
    if value.startswith("/"):
        raise argparse.ArgumentTypeError(
            f"{value!r} is an absolute path; give a path relative to the repo root"
        )
    parts = [part for part in value.split("/") if part not in ("", ".")]
    if ".." in parts:
        raise argparse.ArgumentTypeError(
            f"{value!r} contains '..'; give a path inside the repo without it"
        )
    if not parts:
        raise argparse.ArgumentTypeError(
            f"{value!r} is the repo root itself; name a directory or file inside it"
        )
    return "/".join(parts)


def read_text(root: Path, path: RepoPath) -> str:
    """The file's text, with undecodable bytes replaced and every line ending turned into `\\n`."""
    text = (root / path).read_bytes().decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def finish(problems: Sequence[Problem]) -> int:
    """Print the problems and return the hook's exit status."""
    sys.stdout.write(render(problems))
    return 1 if problems else 0
