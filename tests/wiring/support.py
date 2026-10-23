"""Shared support for wiring tests: running commands in scratch repos and building a hook repo."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

TIMEOUT_SECONDS = 300

ISOLATION = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    # Without this, git on macOS guesses an identity from the user and host name, so a commit that
    # forgot to set one would still succeed.
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "user.useConfigOnly",
    "GIT_CONFIG_VALUE_0": "true",
}


def isolated_env(base: dict[str, str]) -> dict[str, str]:
    """`base` without any `GIT_*` variable, then with the isolation settings applied."""
    env = {key: value for key, value in base.items() if not key.startswith("GIT_")}
    env.update(ISOLATION)
    return env


def run(cmd: Sequence[str | Path], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `cmd` in `cwd` with the cleaned environment, capturing text output; never raises."""
    return subprocess.run(
        [str(part) for part in cmd],
        cwd=cwd,
        env=isolated_env(dict(os.environ)),
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )


def git(repo: Path, *args: str) -> str:
    """Run a git command in `repo` and return its stdout; fails the test on a non-zero exit."""
    result = run(["git", *args], repo)
    assert result.returncode == 0, f"git {' '.join(args)} failed:\n{result.stdout}{result.stderr}"
    return result.stdout


def snapshot_repo(*, source: Path, dest: Path) -> str:
    """Commit `source`'s tracked and untracked non-ignored files, as they sit in its working tree,
    into a new repo at `dest`, and return the commit's sha."""
    listing = git(source, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    paths = dict.fromkeys(path for path in listing.split("\0") if path)
    dest.mkdir(parents=True)
    git(dest, "init", "--quiet", "-b", "main")
    for path in paths:
        origin = source / path
        if not os.path.lexists(origin):
            continue
        target = dest / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target, follow_symlinks=False)
    git(dest, "add", "--all", "--force")
    git(
        dest,
        "-c",
        "user.name=agent-docs-hooks tests",
        "-c",
        "user.email=tests@agent-docs-hooks.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "snapshot",
    )
    return git(dest, "rev-parse", "HEAD").strip()


def script(name: str) -> Path:
    """The console script `name` installed in this test run's environment."""
    return Path(sys.executable).parent / name


def install_hooks(
    *,
    repo: Path,
    hooks: Mapping[str, Sequence[str]],
    hook_repo: tuple[Path, str],
    hook_types: Sequence[str] = ("pre-commit",),
) -> None:
    """Commit a `.pre-commit-config.yaml` naming `hook_repo` by path and sha, with each hook id
    given its args (none when empty), and install pre-commit as each of `hook_types`."""
    path, sha = hook_repo
    lines = ["repos:", f"  - repo: {json.dumps(str(path))}", f"    rev: {sha}", "    hooks:"]
    for hook_id, args in hooks.items():
        lines.append(f"      - id: {hook_id}")
        if args:
            lines.append(f"        args: {json.dumps(list(args))}")
    (repo / ".pre-commit-config.yaml").write_text("\n".join(lines) + "\n")
    git(repo, "add", ".pre-commit-config.yaml")
    git(repo, "commit", "--quiet", "-m", "install hooks")
    types = [arg for hook_type in hook_types for arg in ("--hook-type", hook_type)]
    result = run(pre_commit("install", *types), repo)
    assert result.returncode == 0, result.stdout + result.stderr


def pre_commit(*args: str) -> list[str]:
    """A pre-commit command line run by this test run's interpreter."""
    return [sys.executable, "-m", "pre_commit", *args]


_STATUS_LINE = re.compile(r"(?P<name>[^.]+?)\.{3,}(?P<status>Passed|Failed|.*Skipped)$")


def hook_sections(output: str) -> dict[str, str]:
    """pre-commit's output split per hook: each hook's name maps to its status and the lines
    printed until the next hook's status line."""
    sections: dict[str, str] = {}
    name = None
    for line in output.splitlines():
        status_line = _STATUS_LINE.match(line)
        if status_line:
            name = status_line["name"]
            sections[name] = status_line["status"] + "\n"
        elif name is not None:
            sections[name] += line + "\n"
    return sections
