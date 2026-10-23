"""The effects every hook shares: finding the repo, listing what git tracks, reading, reporting."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agent_docs_hooks.problems import Problem, RepoPath, Skipped, render

_REGULAR_FILE_MODES = frozenset({"100644", "100755"})
_SYMLINK_MODE = "120000"


@dataclass(frozen=True, slots=True)
class Tracked:
    """What git tracks, as the hooks see it."""

    files: frozenset[RepoPath]
    """Regular files that are on disk: the only paths the hooks read."""
    skipped: Mapping[RepoPath, Skipped]
    """Every other tracked path except submodules, with the reason it isn't read."""


def repo_root() -> Path:
    """The top of the git work tree holding the current directory; exits 2 outside one."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(2)
    return Path(result.stdout.rstrip("\n"))


def tracked_files(root: Path) -> Tracked:
    """The tracked regular files on disk, and why each other tracked path is skipped."""
    listing = subprocess.run(
        ["git", "ls-files", "--stage", "-z"], cwd=root, capture_output=True, check=True
    ).stdout
    files = set()
    skipped = {}
    for entry in os.fsdecode(listing).split("\0"):
        if not entry:
            continue
        meta, name = entry.split("\t", 1)
        mode, path, on_disk = meta.split(" ", 1)[0], RepoPath(name), root / name
        if mode == _SYMLINK_MODE or (mode in _REGULAR_FILE_MODES and on_disk.is_symlink()):
            skipped[path] = Skipped.SYMLINK
        elif mode in _REGULAR_FILE_MODES and on_disk.is_file():
            files.add(path)
        elif mode in _REGULAR_FILE_MODES:
            skipped[path] = Skipped.DELETED
    return Tracked(files=frozenset(files), skipped=skipped)


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
    """The file's text as `decode_text` returns it."""
    return decode_text((root / path).read_bytes())


def decode_text(data: bytes) -> str:
    """UTF-8 text with undecodable bytes replaced and every line ending turned into `\\n`."""
    text = data.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def finish(problems: Sequence[Problem]) -> int:
    """Print the problems and return the hook's exit status."""
    sys.stdout.write(render(problems))
    return 1 if problems else 0
