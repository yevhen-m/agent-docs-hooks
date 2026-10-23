from __future__ import annotations

import pytest

from agent_docs_hooks._repo import decode_text
from agent_docs_hooks.budget import (
    Measure,
    budget_subjects,
    check_budget,
    measure,
    untracked_always_loaded,
)
from agent_docs_hooks.problems import Problem, RepoPath


def lines(count: int) -> str:
    """`count` short lines."""
    return "x\n" * count


def chars(count: int) -> str:
    """`count` characters in lines of 100, so the line limits stay out of the way."""
    full, rest = divmod(count, 100)
    return ("x" * 99 + "\n") * full + "x" * rest


def budget_problems(
    path: str, text: str, *, always_loaded: frozenset[str] = frozenset()
) -> list[Problem]:
    limits = budget_subjects(
        tracked=frozenset({RepoPath(path)}),
        docs_root="docs",
        skills_root=".claude/skills",
        always_loaded=always_loaded,
    )
    return check_budget(texts={RepoPath(path): text}, limits=limits)


@pytest.mark.parametrize(
    ("path", "text", "expected"),
    [
        ("CLAUDE.md", lines(200), None),
        ("CLAUDE.md", lines(201), "201 lines (limit 200), ~101 tokens (limit 4,000)"),
        ("CLAUDE.md", chars(16_000), None),
        ("CLAUDE.md", chars(16_001), "161 lines (limit 200), ~4,001 tokens (limit 4,000)"),
        ("docs/a.md", lines(500), None),
        ("docs/a.md", lines(501), "501 lines (limit 500), ~251 tokens (limit 5,000)"),
        ("docs/a.md", chars(20_000), None),
        ("docs/a.md", chars(20_001), "201 lines (limit 500), ~5,001 tokens (limit 5,000)"),
        (
            ".claude/skills/x/SKILL.md",
            lines(501),
            "501 lines (limit 500), ~251 tokens (limit 5,000)",
        ),
        ("sub/AGENTS.md", lines(201), "201 lines (limit 200), ~101 tokens (limit 4,000)"),
        ("README.md", lines(900), None),
    ],
)
def test_limits(path: str, text: str, expected: str | None) -> None:
    problems = budget_problems(path, text)

    assert problems == ([] if expected is None else [Problem(RepoPath(path), None, expected)])


def test_always_loaded_path_gets_the_always_loaded_limit() -> None:
    problems = budget_problems(
        "docs/policy.md", lines(201), always_loaded=frozenset({"docs/policy.md"})
    )

    assert problems == [
        Problem(
            RepoPath("docs/policy.md"), None, "201 lines (limit 200), ~101 tokens (limit 4,000)"
        )
    ]


def test_over_both_limits_is_one_problem_naming_both() -> None:
    text = ("x" * 79 + "\n") * 201

    assert budget_problems("CLAUDE.md", text) == [
        Problem(RepoPath("CLAUDE.md"), None, "201 lines (limit 200), ~4,020 tokens (limit 4,000)")
    ]


def test_crlf_and_lf_measure_the_same() -> None:
    lf = b"line\n" * 10
    crlf = b"line\r\n" * 10

    assert measure(decode_text(crlf)) == measure(decode_text(lf)) == Measure(lines=10, tokens=13)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", Measure(0, 0)),
        ("a\nb", Measure(2, 1)),
        ("a\nb\n", Measure(2, 1)),
        ("abcde", Measure(1, 2)),
    ],
)
def test_measure(text: str, expected: Measure) -> None:
    assert measure(text) == expected


def test_untracked_always_loaded_path_is_a_problem() -> None:
    problems = untracked_always_loaded(
        tracked=frozenset({RepoPath("docs/policy.md")}),
        always_loaded=frozenset({"docs/policy.md", "docs/polcy.md"}),
    )

    assert problems == [
        Problem(RepoPath("docs/polcy.md"), None, "listed with --always-loaded but not tracked")
    ]
