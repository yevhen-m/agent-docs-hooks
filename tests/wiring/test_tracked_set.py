from __future__ import annotations

import os
from pathlib import Path

from support import git, run, script


def write(repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def test_budget_ignores_untracked_and_deleted(scratch_repo: Path) -> None:
    write(scratch_repo, "CLAUDE.md", "x\n" * 201)
    os.symlink("CLAUDE.md", scratch_repo / "AGENTS.md")
    write(scratch_repo, "docs/long.md", "x\n" * 501)
    write(scratch_repo, "docs/deleted.md", "x\n" * 900)
    git(scratch_repo, "add", ".")
    git(scratch_repo, "commit", "--quiet", "-m", "seed")
    (scratch_repo / "docs/deleted.md").unlink()
    write(scratch_repo, "docs/untracked.md", "x\n" * 900)

    result = run([script("agent-docs-budget")], scratch_repo)

    assert (result.returncode, result.stderr) == (1, "")
    assert result.stdout == (
        "CLAUDE.md: 201 lines (limit 200), ~101 tokens (limit 4,000)\n"
        "docs/long.md: 501 lines (limit 500), ~251 tokens (limit 5,000)\n"
    )
