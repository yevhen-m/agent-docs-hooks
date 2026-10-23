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


NO_FRONTMATTER = "# No frontmatter\n"


def test_skills_skips_symlinked_skill_dir(scratch_repo: Path) -> None:
    write(scratch_repo, ".claude/skills/real/SKILL.md", NO_FRONTMATTER)
    write(scratch_repo, "shared/linked/SKILL.md", NO_FRONTMATTER)
    os.symlink("../../shared/linked", scratch_repo / ".claude/skills/linked")
    git(scratch_repo, "add", ".")
    git(scratch_repo, "commit", "--quiet", "-m", "seed")

    result = run([script("agent-docs-skills")], scratch_repo)

    assert (result.returncode, result.stderr) == (1, "")
    assert result.stdout.splitlines() == [
        ".claude/skills/real/SKILL.md: doesn't start with a frontmatter block between two --- lines"
    ]


def test_skills_skips_deleted_skill(scratch_repo: Path) -> None:
    write(scratch_repo, ".claude/skills/gone/SKILL.md", NO_FRONTMATTER)
    git(scratch_repo, "add", ".")
    git(scratch_repo, "commit", "--quiet", "-m", "seed")
    (scratch_repo / ".claude/skills/gone/SKILL.md").unlink()

    result = run([script("agent-docs-skills")], scratch_repo)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_index_targets_are_tracked(scratch_repo: Path) -> None:
    write(scratch_repo, "CLAUDE.md", "Read [the docs](docs/INDEX.md).\n")
    write(
        scratch_repo,
        "docs/INDEX.md",
        "| When | Read |\n"
        "| --- | --- |\n"
        "| Always | [a](a.md) |\n"
        "| Drafting | [draft](draft.md) |\n"
        "| Never | [gone](gone.md) |\n",
    )
    write(scratch_repo, "docs/a.md", "# A\n")
    write(scratch_repo, "docs/gone.md", "# Gone\n")
    git(scratch_repo, "add", ".")
    git(scratch_repo, "commit", "--quiet", "-m", "seed")
    (scratch_repo / "docs/gone.md").unlink()
    write(scratch_repo, "docs/draft.md", "# Draft, untracked\n")
    write(scratch_repo, "docs/unlisted.md", "# Untracked and unlisted\n")

    result = run([script("agent-docs-indexed")], scratch_repo)

    assert (result.returncode, result.stderr) == (1, "")
    assert result.stdout.splitlines() == [
        "docs/INDEX.md:4: docs/draft.md doesn't exist or isn't tracked by git",
        "docs/INDEX.md:5: docs/gone.md doesn't exist or isn't tracked by git",
    ]
