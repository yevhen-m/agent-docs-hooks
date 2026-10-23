from __future__ import annotations

import os
from pathlib import Path

from support import git, snapshot_repo

from agent_docs_hooks._repo import tracked_files


def test_tracked_files_excludes_untracked_symlinks_and_deleted(scratch_repo: Path) -> None:
    (scratch_repo / "kept.md").write_text("kept\n")
    (scratch_repo / "gone.md").write_text("gone\n")
    os.symlink("kept.md", scratch_repo / "link.md")
    git(scratch_repo, "add", "kept.md", "gone.md", "link.md")
    git(scratch_repo, "commit", "--quiet", "-m", "seed")
    (scratch_repo / "gone.md").unlink()
    (scratch_repo / "untracked.md").write_text("untracked\n")

    assert tracked_files(scratch_repo) == {"kept.md"}


def test_snapshot_repo(scratch_repo: Path, tmp_path: Path) -> None:
    (scratch_repo / ".gitignore").write_text("*.log\n")
    (scratch_repo / "edited.md").write_text("committed\n")
    (scratch_repo / "gone.md").write_text("gone\n")
    git(scratch_repo, "add", ".")
    git(scratch_repo, "commit", "--quiet", "-m", "seed")
    (scratch_repo / "edited.md").write_text("uncommitted edit\n")
    (scratch_repo / "gone.md").unlink()
    (scratch_repo / "new.md").write_text("untracked\n")
    (scratch_repo / "ignored.log").write_text("ignored\n")
    dest = tmp_path / "snapshot"

    sha = snapshot_repo(source=scratch_repo, dest=dest)

    assert git(dest, "ls-tree", "-r", "--name-only", sha).split() == [
        ".gitignore",
        "edited.md",
        "new.md",
    ]
    assert git(dest, "show", f"{sha}:edited.md") == "uncommitted edit\n"
