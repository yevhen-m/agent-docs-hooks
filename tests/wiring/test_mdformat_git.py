from __future__ import annotations

from pathlib import Path

import pytest
from support import git, install_hooks, pre_commit, run, script

UNFORMATTED = "# Doc\n\n* one\n* two\n"
FORMATTED = "# Doc\n\n- one\n- two\n"
WORDS = " ".join(["word"] * 30)
WRAPPED = " ".join(["word"] * 20) + "\n" + " ".join(["word"] * 10) + "\n"


@pytest.fixture
def repo(scratch_repo: Path, hook_repo_commit: tuple[Path, str]) -> Path:
    install_hooks(repo=scratch_repo, hooks={"mdformat": []}, hook_repo=hook_repo_commit)
    return scratch_repo


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def test_commit_fails_then_succeeds(repo: Path) -> None:
    (repo / "doc.md").write_text(UNFORMATTED)
    git(repo, "add", "doc.md")
    staged = git(repo, "diff", "--cached")
    before = head(repo)

    first = run(["git", "commit", "-m", "add doc"], repo)

    assert first.returncode != 0
    assert "doc.md: reformatted\n" in first.stdout + first.stderr
    assert head(repo) == before
    assert (repo / "doc.md").read_text() == FORMATTED
    assert git(repo, "diff", "--cached") == staged
    assert git(repo, "diff", "--name-only") == "doc.md\n"

    git(repo, "add", "doc.md")
    second = run(["git", "commit", "-m", "add doc"], repo)

    assert second.returncode == 0, second.stdout + second.stderr
    assert git(repo, "show", "HEAD:doc.md") == FORMATTED


@pytest.mark.parametrize(
    ("config", "status", "expected"),
    [(None, 1, WRAPPED), ('wrap = "keep"\n', 0, WORDS + "\n")],
)
def test_root_config_changes_output(
    repo: Path, config: str | None, status: int, expected: str
) -> None:
    if config is not None:
        (repo / ".mdformat.toml").write_text(config)
    (repo / "long.md").write_text(WORDS + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "--no-verify", "-m", "seed")

    result = run(pre_commit("run", "mdformat", "--all-files"), repo)

    assert result.returncode == status, result.stdout + result.stderr
    assert (repo / "long.md").read_text() == expected


def partially_staged(repo: Path) -> tuple[str, str]:
    """Commit a formatted doc, stage an unformatted edit to its list, then edit the same lines
    again without staging. Returns the staged diff and the unstaged working-tree text."""
    (repo / "doc.md").write_text(FORMATTED)
    git(repo, "add", "doc.md")
    git(repo, "commit", "--quiet", "-m", "seed")
    (repo / "doc.md").write_text("# Doc\n\n* one staged\n* two\n")
    git(repo, "add", "doc.md")
    unstaged = "# Doc\n\n* one unstaged\n* two\n"
    (repo / "doc.md").write_text(unstaged)
    return git(repo, "diff", "--cached"), unstaged


def test_partially_staged_keeps_unstaged_edit(repo: Path) -> None:
    staged, unstaged = partially_staged(repo)
    before = head(repo)

    commit = run(["git", "commit", "-m", "edit doc"], repo)

    assert commit.returncode != 0
    # The scenario that makes re-staging lose work: the fix conflicts with the stashed edit.
    assert "Stashed changes conflicted with hook auto-fixes" in commit.stderr
    assert head(repo) == before
    assert (repo / "doc.md").read_text() == unstaged
    assert git(repo, "diff", "--cached") == staged

    fix = run(pre_commit("run", "mdformat", "--files", "doc.md"), repo)

    assert fix.returncode == 1, fix.stdout + fix.stderr
    assert "doc.md: reformatted\n" in fix.stdout
    assert (repo / "doc.md").read_text() == "# Doc\n\n- one unstaged\n- two\n"
    assert git(repo, "diff", "--cached") == staged


def test_all_files_leaves_index(repo: Path) -> None:
    staged, _ = partially_staged(repo)

    result = run(pre_commit("run", "--all-files"), repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert (repo / "doc.md").read_text() == "# Doc\n\n- one unstaged\n- two\n"
    assert git(repo, "diff", "--cached") == staged


def test_file_mdformat_cant_read_is_named_and_the_rest_are_formatted(scratch_repo: Path) -> None:
    (scratch_repo / "a.md").write_text("* one\n* two\n")
    (scratch_repo / "b.md").write_bytes(b"caf\xe9\n")
    (scratch_repo / "c.md").write_text("* three\n")

    result = run([script("agent-docs-mdformat"), "a.md", "b.md", "c.md"], scratch_repo)

    assert result.returncode == 1
    assert "Traceback" not in result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "b.md: isn't saved as UTF-8, so mdformat can't read it; save it as UTF-8",
        "a.md: reformatted",
        "c.md: reformatted",
    ]
    assert (scratch_repo / "a.md").read_text() == "- one\n- two\n"
    assert (scratch_repo / "b.md").read_bytes() == b"caf\xe9\n"
    assert (scratch_repo / "c.md").read_text() == "- three\n"
