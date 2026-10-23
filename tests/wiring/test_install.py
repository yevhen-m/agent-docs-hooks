from __future__ import annotations

from pathlib import Path

from support import git, hook_sections, install_hooks, pre_commit, run

HOOK_IDS = ("doc-budget", "docs-indexed", "skills", "doc-links", "mdformat")

CONVENTIONAL = {
    "CLAUDE.md": "Read [the docs](docs/INDEX.md).\n",
    "docs/INDEX.md": (
        "# Docs\n\n"
        "| When              | Read      |\n"
        "| ----------------- | --------- |\n"
        "| Before changing A | [a](a.md) |\n"
    ),
    "docs/a.md": "# A\n\nSee [the skill](../.claude/skills/my-skill/SKILL.md#my-skill).\n",
    ".claude/skills/my-skill/SKILL.md": (
        "---\nname: my-skill\ndescription: Does one thing.\n---\n\n# My skill\n"
    ),
}


def write(repo: Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def run_all(repo: Path) -> tuple[int, dict[str, str], str]:
    """Commit what's in the tree, run every hook on all files, and split the output per hook."""
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "--no-verify", "-m", "tree")
    result = run(pre_commit("run", "--all-files"), repo)
    output = result.stdout + result.stderr
    return result.returncode, hook_sections(output), output


def test_defaults(scratch_repo: Path, tmp_path: Path, hook_repo_commit: tuple[Path, str]) -> None:
    hooks = dict.fromkeys(HOOK_IDS, ())
    install_hooks(repo=scratch_repo, hooks=hooks, hook_repo=hook_repo_commit)
    write(scratch_repo, CONVENTIONAL)

    status, sections, output = run_all(scratch_repo)

    assert status == 0, output
    assert set(sections) == {"doc budget", "docs indexed", "skills", "doc links", "mdformat"}

    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, "init", "--quiet", "-b", "main")
    git(empty, "config", "user.name", "Scratch")
    git(empty, "config", "user.email", "scratch@agent-docs-hooks.invalid")
    install_hooks(repo=empty, hooks=hooks, hook_repo=hook_repo_commit)
    write(empty, {"notes.txt": "No markdown here.\n"})

    status, _, output = run_all(empty)

    assert status == 0, output

    write(
        scratch_repo,
        {
            "AGENTS.md": "\n\n".join(["x"] * 101) + "\n",
            "docs/unlisted.md": "# Unlisted\n",
            ".claude/skills/my-skill/SKILL.md": (
                "---\nname: other-name\ndescription: Does one thing.\n---\n\n# My skill\n"
            ),
            "broken.md": "[gone](gone.md)\n",
            "messy.md": "* one\n* two\n",
        },
    )

    status, sections, output = run_all(scratch_repo)

    assert status == 1, output
    assert all(section.startswith("Failed") for section in sections.values()), output
    assert "AGENTS.md: 201 lines (limit 200)" in sections["doc budget"]
    assert "docs/unlisted.md: isn't listed in docs/INDEX.md" in sections["docs indexed"]
    assert ".claude/skills/my-skill/SKILL.md:2: name other-name" in sections["skills"]
    assert "[broken.md]:" in sections["doc links"]
    assert "messy.md: reformatted" in sections["mdformat"]


def test_args(scratch_repo: Path, hook_repo_commit: tuple[Path, str]) -> None:
    layout = ["--docs-root", "documentation", "--skills-root", "agents/skills"]
    install_hooks(
        repo=scratch_repo,
        hooks={
            "doc-budget": [*layout, "--always-loaded", "notes/rules.md"],
            "docs-indexed": ["--docs-root", "documentation"],
            "skills": ["--skills-root", "agents/skills"],
        },
        hook_repo=hook_repo_commit,
    )
    index = "| When | Read |\n| --- | --- |\n| Before A | [a](a.md) |\n| Long | [long](long.md) |\n"
    write(
        scratch_repo,
        {
            "CLAUDE.md": "Read [the docs](documentation/INDEX.md).\n",
            "documentation/INDEX.md": index,
            "documentation/a.md": "# A\n",
            "documentation/long.md": "x\n" * 501,
            "documentation/unlisted.md": "# Unlisted\n",
            "agents/skills/bad/SKILL.md": "---\nname: wrong\ndescription: Does a thing.\n---\n",
            "agents/skills/big/SKILL.md": "---\nname: big\ndescription: Big.\n---\n" + "x\n" * 501,
            "notes/rules.md": "x\n" * 201,
        },
    )

    status, sections, output = run_all(scratch_repo)

    assert status == 1, output
    assert sections["doc budget"].startswith("Failed"), output
    for path in ("agents/skills/big/SKILL.md", "documentation/long.md", "notes/rules.md"):
        assert f"{path}: " in sections["doc budget"], output
    assert (
        "documentation/unlisted.md: isn't listed in documentation/INDEX.md"
        in (sections["docs indexed"])
    )
    assert (
        "agents/skills/bad/SKILL.md:2: name wrong doesn't match its directory bad"
        in (sections["skills"])
    )

    write(
        scratch_repo,
        {
            "documentation/INDEX.md": index + "| Unlisted | [unlisted](unlisted.md) |\n",
            "documentation/long.md": "x\n" * 500,
            "agents/skills/bad/SKILL.md": "---\nname: bad\ndescription: Does a thing.\n---\n",
            "agents/skills/big/SKILL.md": "---\nname: big\ndescription: Big.\n---\n",
            "notes/rules.md": "x\n" * 200,
        },
    )

    status, sections, output = run_all(scratch_repo)

    assert status == 0, output
