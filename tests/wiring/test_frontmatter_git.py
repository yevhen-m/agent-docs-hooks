from __future__ import annotations

from pathlib import Path

from support import git, run, script


def test_tracked_set_scope_config_and_references(scratch_repo: Path) -> None:
    docs = scratch_repo / "notes"
    docs.mkdir()
    (docs / "a.md").write_text("---\nstatus: open\nsupersedes: notes/old.md\n---\n")
    (docs / "old.md").write_text("# Old\n")
    (scratch_repo / "unrelated.md").write_text("---\naliases: [unrelated]\n---\n")
    git(scratch_repo, "add", ".")
    command = [script("agent-docs-frontmatter"), "--docs-root", "notes"]
    assert run(command, scratch_repo).returncode == 0

    # The target exists, but isn't tracked; a local file must not hide a broken checkout.
    git(scratch_repo, "rm", "--cached", "notes/old.md")
    result = run(command, scratch_repo)
    assert result.returncode == 1
    assert "notes/a.md:3: supersedes: reference 'notes/old.md'" in result.stdout
    git(scratch_repo, "add", "notes/old.md")
    (docs / "old.md").unlink()
    (docs / "old.md").symlink_to("a.md")
    assert run(command, scratch_repo).returncode == 1
    (docs / "old.md").unlink()
    assert run(command, scratch_repo).returncode == 1
    (docs / "old.md").write_text("# Old\n")

    (scratch_repo / ".frontmatter.yaml").write_text("default-allowed: []\n")
    result = run(command, scratch_repo)
    assert result.returncode == 1
    assert "status is not allowed here" in result.stdout
    config = scratch_repo / "policy.yaml"
    config.write_text("default-allowed: [status, supersedes]\n")
    assert run([*command, "--config", "policy.yaml"], scratch_repo).returncode == 0
    config.write_text("defalt-allowed: []\n")
    result = run([*command, "--config", "policy.yaml"], scratch_repo)
    assert result.returncode == 2
    assert "unknown setting" in result.stderr
    result = run([*command, "--config", "missing.yaml"], scratch_repo)
    assert result.returncode == 2
    assert "missing.yaml" in result.stderr


def test_no_docs_and_invalid_config(scratch_repo: Path) -> None:
    command = [script("agent-docs-frontmatter")]
    assert run(command, scratch_repo).returncode == 0
    config = scratch_repo / ".frontmatter.yaml"
    config.write_text("rules: invalid\n")
    assert run(command, scratch_repo).returncode == 2
