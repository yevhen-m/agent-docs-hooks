from __future__ import annotations

import pytest

from agent_docs_hooks.mdformat_hook import format_args


@pytest.mark.parametrize(
    ("has_root_config", "expected"),
    [
        (
            False,
            [
                "--wrap",
                "100",
                "--number",
                "--end-of-line",
                "lf",
                "--extensions",
                "frontmatter",
                "--extensions",
                "gfm",
                "--",
                "a.md",
                "docs/b.md",
            ],
        ),
        (True, ["--", "a.md", "docs/b.md"]),
    ],
)
def test_options_with_and_without_root_config(has_root_config: bool, expected: list[str]) -> None:
    assert format_args(has_root_config=has_root_config, paths=["a.md", "docs/b.md"]) == expected
