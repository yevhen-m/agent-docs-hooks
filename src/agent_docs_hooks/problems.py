"""What a check reports, and how a hook prints it."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import NewType

RepoPath = NewType("RepoPath", str)
"""A repo-relative POSIX path, as `git ls-files` prints it."""


@dataclass(frozen=True, slots=True)
class Problem:
    path: RepoPath
    line: int | None
    message: str


def _order(problem: Problem) -> tuple[str, int, str]:
    return (problem.path, -1 if problem.line is None else problem.line, problem.message)


def render(problems: Iterable[Problem]) -> str:
    """One `<path>[:<line>]: <message>` line per problem, sorted by path then line."""
    lines = []
    for problem in sorted(problems, key=_order):
        where = problem.path if problem.line is None else f"{problem.path}:{problem.line}"
        lines.append(f"{where}: {problem.message}\n")
    return "".join(lines)
