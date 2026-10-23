from __future__ import annotations

from pathlib import Path

import pytest
from support import git, run, script


def links(repo: Path, files: dict[str, str]) -> tuple[int, str]:
    """Commit `files` and run `agent-docs-links`; returns its exit status and combined output."""
    for path, text in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "seed")
    result = run([script("agent-docs-links")], repo)
    return result.returncode, result.stdout + result.stderr


def test_missing_file_fails_naming_the_citing_file(scratch_repo: Path) -> None:
    status, output = links(scratch_repo, {"cites.md": "[gone](gone.md)\n", "other.md": "# Other\n"})

    assert status != 0
    assert "[cites.md]:" in output
    assert "gone.md" in output
    assert "[other.md]:" not in output


def test_missing_anchor_fails_naming_the_citing_file(scratch_repo: Path) -> None:
    status, output = links(
        scratch_repo, {"cites.md": "[part](target.md#nope)\n", "target.md": "# Real heading\n"}
    )

    assert status != 0
    assert "[cites.md]:" in output
    assert "target.md#nope" in output


def test_http_link_is_never_fetched(scratch_repo: Path) -> None:
    status, output = links(scratch_repo, {"a.md": "[closed port](http://127.0.0.1:9/)\n"})

    assert status == 0, output


def test_directory_link_passes(scratch_repo: Path) -> None:
    status, output = links(
        scratch_repo, {"a.md": "[docs](docs/) and [docs again](docs)\n", "docs/b.md": "# B\n"}
    )

    assert status == 0, output


@pytest.mark.parametrize(("link", "passes"), [("/docs/b.md", True), ("/docs/missing.md", False)])
def test_root_relative_link_resolves_against_repo_root(
    scratch_repo: Path, link: str, passes: bool
) -> None:
    status, output = links(scratch_repo, {"sub/a.md": f"[b]({link})\n", "docs/b.md": "# B\n"})

    assert (status == 0) is passes, output


def test_root_lychee_toml_exclusion_is_applied(scratch_repo: Path) -> None:
    status, output = links(
        scratch_repo,
        {
            "lychee.toml": 'exclude = ["excluded\\\\.md"]\n',
            "a.md": "[excluded](excluded.md)\n",
        },
    )

    assert status == 0, output


def test_github_anchor_variants_pass(scratch_repo: Path) -> None:
    target = (
        "# Repeated\n\n# Repeated\n\n# Foo: Bar!\n\n# `code` here\n\n# Ünïcode\n\n"
        '<a id="custom"></a>\n\nText.\n'
    )
    cites = (
        "[a](target.md#repeated) [b](target.md#repeated-1) [c](target.md#foo-bar)\n"
        "[d](target.md#code-here) [e](target.md#ünïcode) [f](target.md#custom)\n"
        "[g](#local)\n\n## Local\n"
    )

    status, output = links(scratch_repo, {"target.md": target, "cites.md": cites})

    assert status == 0, output


def test_no_markdown_passes_without_running_lychee(scratch_repo: Path) -> None:
    status, output = links(scratch_repo, {"a.txt": "[x](missing.md)\n"})

    assert (status, output) == (0, "")


def test_paths_with_glob_characters_are_read_as_written(scratch_repo: Path) -> None:
    files = {
        "app/[slug]/README.md": "[gone](gone-slug.md)\n",
        "docs/[draft].md": "[gone](gone-draft.md)\n",
        "docs/d.md": "[gone](gone-d.md)\n",
        "notes/a*.md": "[gone](gone-star.md)\n",
        "notes/ab.md": "[gone](gone-ab.md)\n",
        "notes/q?.md": "[gone](gone-question.md)\n",
        "notes/qx.md": "[gone](gone-qx.md)\n",
    }

    status, output = links(scratch_repo, files)

    assert status != 0
    for path, text in files.items():
        target = text[len("[gone](") : -len(")\n")]
        assert output.count(f"[{path}]:") == 1, output
        assert output.count(f"/{target} ") == 1, output
