from __future__ import annotations

import os
from pathlib import Path

from support import git, hook_sections, install_hooks, run, script


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
        "docs/INDEX.md:5: docs/gone.md is tracked by git but missing from disk; "
        "restore it or remove this row",
    ]


def test_deletion_only_commit_fails(scratch_repo: Path, hook_repo_commit: tuple[Path, str]) -> None:
    install_hooks(
        repo=scratch_repo,
        hooks={"doc-links": [], "docs-indexed": []},
        hook_repo=hook_repo_commit,
    )
    write(scratch_repo, "CLAUDE.md", "Read [the docs](docs/INDEX.md).\n")
    write(
        scratch_repo,
        "docs/INDEX.md",
        "| When | Read |\n| --- | --- |\n| Before A | [a](a.md) |\n| Before B | [b](b.md) |\n",
    )
    write(scratch_repo, "docs/a.md", "# A\n")
    write(scratch_repo, "docs/b.md", "# B\n")
    write(scratch_repo, "README.md", "See [a](docs/a.md).\n")
    git(scratch_repo, "add", ".")
    clean = run(["git", "commit", "-m", "seed"], scratch_repo)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    before = git(scratch_repo, "rev-parse", "HEAD")

    git(scratch_repo, "rm", "--quiet", "docs/a.md")
    result = run(["git", "commit", "-m", "remove a"], scratch_repo)

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert git(scratch_repo, "rev-parse", "HEAD") == before
    sections = hook_sections(output)
    assert sections["doc links"].startswith("Failed"), output
    assert "[README.md]:" in sections["doc links"]
    assert sections["docs indexed"].startswith("Failed"), output
    assert (
        "docs/INDEX.md:3: docs/a.md doesn't exist or isn't tracked by git"
        in sections["docs indexed"]
    )
