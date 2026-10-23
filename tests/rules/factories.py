"""Fresh input values for rule tests. Every factory takes keyword overrides only."""

from __future__ import annotations

from agent_docs_hooks.problems import Problem, RepoPath


def problem(*, path: str = "docs/a.md", line: int | None = None, message: str = "bad") -> Problem:
    return Problem(path=RepoPath(path), line=line, message=message)
