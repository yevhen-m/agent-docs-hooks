from __future__ import annotations

import argparse

import pytest
from factories import problem

from agent_docs_hooks._repo import normalize_root
from agent_docs_hooks.problems import render


def test_render_sorts_and_formats() -> None:
    problems = [
        problem(path="b.md", line=3, message="third line"),
        problem(path="a.md", line=10, message="tenth line"),
        problem(path="b.md", line=None, message="whole file"),
        problem(path="a.md", line=2, message="second line"),
        problem(path="b.md", line=1, message="first line"),
    ]

    assert render(problems) == (
        "a.md:2: second line\n"
        "a.md:10: tenth line\n"
        "b.md: whole file\n"
        "b.md:1: first line\n"
        "b.md:3: third line\n"
    )


def test_render_nothing_is_empty() -> None:
    assert render([]) == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [("./docs/", "docs"), ("docs", "docs"), ("claude/skills/", "claude/skills")],
)
def test_normalize_root(value: str, expected: str) -> None:
    assert normalize_root(value) == expected


@pytest.mark.parametrize("value", ["/abs", "a/../b", "..", ".", "./"])
def test_normalize_root_rejects(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        normalize_root(value)
