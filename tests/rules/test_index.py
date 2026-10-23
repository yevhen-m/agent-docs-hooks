from __future__ import annotations

import pytest
from factories import index_md

from agent_docs_hooks.index import BadRow, Entry, check_index, index_inputs, parse_rows
from agent_docs_hooks.problems import Problem, RepoPath, Skipped

LINKED = "Start with [the docs](docs/INDEX.md).\n"
ROOT_INDEX = RepoPath("docs/INDEX.md")


def check(
    files: dict[str, str],
    *,
    docs_root: str = "docs",
    skipped: dict[str, Skipped] | None = None,
) -> list[Problem]:
    tracked = frozenset(RepoPath(path) for path in files)
    read = index_inputs(tracked=tracked, docs_root=docs_root)
    texts = {path: files[path] for path in read}
    return check_index(
        tracked=tracked,
        skipped={RepoPath(path): why for path, why in (skipped or {}).items()},
        docs_root=docs_root,
        texts=texts,
    )


def tree() -> dict[str, str]:
    """A valid tree: one doc, listed in the root index, which the root CLAUDE.md links."""
    return {
        "CLAUDE.md": LINKED,
        "docs/INDEX.md": index_md(rows=[("Before changing A", "[a](a.md)")]),
        "docs/a.md": "# A\n",
    }


def problem(path: str, line: int | None, message: str) -> Problem:
    return Problem(path=RepoPath(path), line=line, message=message)


def test_valid_tree_passes() -> None:
    assert check(tree()) == []


def test_no_docs_passes() -> None:
    assert check({"README.md": "# Hi\n", "docs/notes.txt": "x\n"}) == []


def test_doc_too_deep() -> None:
    files = tree()
    files["docs/a/b/c.md"] = "# C\n"

    assert check(files) == [
        problem("docs/a/b/c.md", None, "is too deep; docs go in docs/ or one directory below it")
    ]


MISSING = "is missing; a directory with docs needs an INDEX.md that lists them"


def test_missing_root_index_is_one_problem() -> None:
    files = {"CLAUDE.md": LINKED, "docs/a.md": "# A\n", "docs/b.md": "# B\n"}

    assert check(files) == [problem("docs/INDEX.md", None, MISSING)]


def test_missing_subdirectory_index_is_one_problem() -> None:
    files = tree()
    files["docs/sub/x.md"] = "# X\n"

    assert check(files) == [problem("docs/sub/INDEX.md", None, MISSING)]


def test_doc_missing_from_its_index() -> None:
    files = tree()
    files["docs/b.md"] = "# B\n"

    assert check(files) == [problem("docs/b.md", None, "isn't listed in docs/INDEX.md")]


def test_doc_listed_twice() -> None:
    files = tree()
    files["docs/INDEX.md"] = index_md(rows=[("Before A", "[a](a.md)"), ("Also A", "[again](a.md)")])

    assert check(files) == [problem("docs/INDEX.md", 4, "docs/a.md is already listed on line 3")]


@pytest.mark.parametrize(
    ("cell", "extra", "message"),
    [
        ("[gone](gone.md)", {}, "docs/gone.md doesn't exist or isn't tracked by git"),
        (
            "[other](../README.md)",
            {"README.md": "# R\n"},
            "README.md is in another directory; list it in that directory's INDEX.md",
        ),
        (
            "[nested](sub/x.md)",
            {"docs/sub/x.md": "# X\n", "docs/sub/INDEX.md": index_md(rows=[("X", "[x](x.md)")])},
            "docs/sub/x.md is in another directory; list it in that directory's INDEX.md",
        ),
        ("[notes](notes.txt)", {"docs/notes.txt": "x\n"}, "docs/notes.txt isn't a markdown file"),
    ],
)
def test_entry_target_must_be_a_tracked_doc_in_the_same_directory(
    cell: str, extra: dict[str, str], message: str
) -> None:
    files = tree()
    files.update(extra)
    rows = [("Before A", "[a](a.md)"), ("Bad", cell)]
    if "docs/sub/INDEX.md" in extra:
        rows.append(("Sub", "[sub](sub/INDEX.md)"))
    files["docs/INDEX.md"] = index_md(rows=rows)

    assert check(files) == [problem("docs/INDEX.md", 4, message)]


def test_subdirectory_index_missing_from_root_index() -> None:
    files = tree()
    files["docs/sub/x.md"] = "# X\n"
    files["docs/sub/INDEX.md"] = index_md(rows=[("Before X", "[x](x.md)")])

    assert check(files) == [problem("docs/sub/INDEX.md", None, "isn't listed in docs/INDEX.md")]


def test_subdirectory_index_listed_twice() -> None:
    files = tree()
    files["docs/sub/x.md"] = "# X\n"
    files["docs/sub/INDEX.md"] = index_md(rows=[("Before X", "[x](x.md)")])
    files["docs/INDEX.md"] = index_md(
        rows=[
            ("Before A", "[a](a.md)"),
            ("Sub", "[sub](sub/INDEX.md)"),
            ("Sub", "[s](sub/INDEX.md)"),
        ]
    )

    assert check(files) == [
        problem("docs/INDEX.md", 5, "docs/sub/INDEX.md is already listed on line 4")
    ]


def test_subdirectory_index_listed_in_root_passes() -> None:
    files = tree()
    files["docs/sub/x.md"] = "# X\n"
    files["docs/sub/INDEX.md"] = index_md(rows=[("Before X", "[x](x.md)")])
    files["docs/INDEX.md"] = index_md(
        rows=[("Before A", "[a](a.md)"), ("Sub", "[sub](sub/INDEX.md)")]
    )

    assert check(files) == []


@pytest.mark.parametrize(
    ("trigger", "cell", "message"),
    [
        ("", "[a](a.md)", "row has no trigger in its first cell"),
        ("Before A", "[a](a.md) [b](b.md)", "row's second cell has more than one link"),
        ("Before A", "a.md", "row's second cell needs a link to a doc"),
        (
            "Before A",
            "[a](https://example.com/a.md)",
            "row's link must point at a file in this repo, not a URL",
        ),
    ],
)
def test_bad_row(trigger: str, cell: str, message: str) -> None:
    files = tree()
    files["docs/b.md"] = "# B\n"
    files["docs/INDEX.md"] = index_md(rows=[(trigger, cell), ("Before B", "[b](b.md)")])

    assert check(files) == [
        problem("docs/INDEX.md", 3, message),
        problem("docs/a.md", None, "isn't listed in docs/INDEX.md"),
    ]


def test_second_table_with_valid_rows_passes() -> None:
    files = tree()
    files["docs/b.md"] = "# B\n"
    files["docs/INDEX.md"] = (
        index_md(rows=[("Before A", "[a](a.md)")])
        + "\n## More\n\n"
        + index_md(rows=[("Before B", "[b](b.md)")])
    )

    assert check(files) == []


def test_plain_text_row_fails_even_next_to_a_valid_row_for_the_same_doc() -> None:
    files = tree()
    files["docs/INDEX.md"] = index_md(rows=[("Before A", "[a](a.md)"), ("Also A", "a.md")])

    assert check(files) == [problem("docs/INDEX.md", 4, "row's second cell needs a link to a doc")]


def test_links_in_prose_are_ignored() -> None:
    files = tree()
    files["docs/INDEX.md"] = (
        "Read [the missing one](gone.md) and [the readme](../README.md).\n\n"
        + index_md(rows=[("Before A", "[a](a.md)")])
    )

    assert check(files) == []


def test_link_with_fragment_counts_as_the_doc() -> None:
    files = tree()
    files["docs/my doc.md"] = "# Mine\n"
    files["docs/INDEX.md"] = index_md(
        rows=[("Before A", "[a](a.md#part)"), ("Mine", "[mine](my%20doc.md?x=1)")]
    )

    assert check(files) == []


NOT_LINKED = problem("docs/INDEX.md", None, "isn't linked from the root CLAUDE.md or AGENTS.md")


@pytest.mark.parametrize(
    ("root_files", "expected"),
    [
        ({"CLAUDE.md": LINKED}, []),
        ({"CLAUDE.md": "# No link\n", "AGENTS.md": LINKED}, []),
        ({"AGENTS.md": LINKED}, []),
        ({"CLAUDE.md": "See docs/INDEX.md.\n", "AGENTS.md": "# None\n"}, [NOT_LINKED]),
        ({}, [NOT_LINKED]),
        ({"CLAUDE.md": "```\n[docs](docs/INDEX.md)\n```\n"}, [NOT_LINKED]),
        ({"CLAUDE.md": "    [docs](docs/INDEX.md)\n"}, [NOT_LINKED]),
        ({"sub/CLAUDE.md": "[docs](../docs/INDEX.md)\n"}, [NOT_LINKED]),
    ],
)
def test_root_index_is_linked_from_root_instructions(
    root_files: dict[str, str], expected: list[Problem]
) -> None:
    files = tree()
    del files["CLAUDE.md"]
    files.update(root_files)

    assert check(files) == expected


def test_parse_rows() -> None:
    text = index_md(rows=[("Before A", "[a](a.md)"), ("", "[b](b.md)")])

    assert parse_rows(index_path=ROOT_INDEX, text=text) == [
        Entry(trigger="Before A", target=RepoPath("docs/a.md"), line=3),
        BadRow(line=4, reason="row has no trigger in its first cell"),
    ]


@pytest.mark.parametrize(
    ("why", "message"),
    [
        (
            Skipped.SYMLINK,
            "docs/b.md is a symlink, which the hooks don't follow; "
            "replace it with the file itself or remove this row",
        ),
        (
            Skipped.DELETED,
            "docs/b.md is tracked by git but missing from disk; restore it or remove this row",
        ),
    ],
)
def test_entry_for_a_tracked_path_the_hook_cant_read_says_why(why: Skipped, message: str) -> None:
    files = tree()
    files["docs/INDEX.md"] = index_md(
        rows=[("Before changing A", "[a](a.md)"), ("Before changing B", "[b](b.md)")]
    )

    assert check(files, skipped={"docs/b.md": why}) == [problem("docs/INDEX.md", 4, message)]


@pytest.mark.parametrize(
    ("why", "message"),
    [
        (
            Skipped.SYMLINK,
            "is a symlink, which the hooks don't follow; replace it with the file itself",
        ),
        (Skipped.DELETED, "is tracked by git but missing from disk; restore it"),
    ],
)
def test_index_git_tracks_but_the_hook_cant_read_says_why(why: Skipped, message: str) -> None:
    files = tree()
    files["docs/s/c.md"] = "# C\n"

    problems = check(files, skipped={"docs/s/INDEX.md": why})

    assert problem("docs/s/INDEX.md", None, message) in problems
