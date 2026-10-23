from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from support import ISOLATION, git, snapshot_repo

CHECKOUT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def _isolated_environment(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Strip every `GIT_*` variable for the whole wiring session, so nothing a test runs, in
    process or as a child, can reach this checkout's own `.git` or the developer's git config,
    and share one `PRE_COMMIT_HOME` so hook environments are built once per session."""
    with pytest.MonkeyPatch.context() as patch:
        for key in [key for key in os.environ if key.startswith("GIT_")]:
            patch.delenv(key)
        for key, value in ISOLATION.items():
            patch.setenv(key, value)
        patch.setenv("PRE_COMMIT_HOME", str(tmp_path_factory.mktemp("pre-commit-home")))
        yield


@pytest.fixture
def scratch_repo(tmp_path: Path) -> Path:
    """A fresh git repo on `main` with a local identity and signing off."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet", "-b", "main")
    git(repo, "config", "user.name", "Scratch")
    git(repo, "config", "user.email", "scratch@agent-docs-hooks.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    return repo


@pytest.fixture(scope="session")
def hook_repo_commit(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """A temporary git repo holding one commit of this checkout's working tree, and its sha."""
    dest = tmp_path_factory.mktemp("hook-repo") / "agent-docs-hooks"
    return dest, snapshot_repo(source=CHECKOUT, dest=dest)
