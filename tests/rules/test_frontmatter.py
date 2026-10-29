from __future__ import annotations

import pytest

from agent_docs_hooks.frontmatter import check_frontmatter
from agent_docs_hooks.frontmatter_policy import parse_policy
from agent_docs_hooks.problems import RepoPath


def messages(yaml: str, *, path: str = "docs/note.md", config: str | None = None) -> list[str]:
    return [
        problem.message
        for problem in check_frontmatter(
            texts={RepoPath(path): f"---\n{yaml}\n---\n\n# Note\n"},
            tracked=frozenset({RepoPath(path), RepoPath("docs/previous.md")}),
            policy=parse_policy(config),
        )
    ]


def test_generic_fields_accept_useful_metadata_without_collection_names() -> None:
    assert not messages(
        "status: open\n"
        "date: '2026-10-29'\n"
        "supersedes: docs/previous.md\n"
        "superseded-by: [https://example.com/history]\n"
        "last-reviewed: 2026-10-29\n"
        "review-every: 3mo\n"
        "invalidated-by:\n  - Customer evidence changes\n"
        "source-type: interview\n"
        "date-captured: 2024-02-29\n"
        "origin: |\n  Customer conversation\n  Captured with consent\n"
        "evidence-date: 2026-10-01"
    )
    assert not messages("status: on")  # YAML 1.2 string, rather than a YAML 1.1 boolean.
    assert not messages("origin: |\n  ---\n  Transcript separator")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("", "invalid frontmatter"),
        ("[]", "invalid frontmatter"),
        ("- status: open", "invalid frontmatter"),
        ("status: [unfinished", "invalid frontmatter"),
        ("status: open\nstatus: accepted", "duplicate key status"),
        ("status: {a: one, a: two}", "duplicate key a"),
        ("true: yes", "keys must be strings"),
        ("status: !!python/object:builtins.object {}", "invalid frontmatter"),
        ("aliases: [legacy]", "aliases is not allowed"),
        ("status: null", "status must be a nonempty string"),
        ("status: ''", "status must be a nonempty string"),
        ("status: '  '", "status must be a nonempty string"),
        ("status: []", "status must be a nonempty string"),
        ("status: {}", "status must be a nonempty string"),
        ("status: true", "status must be a nonempty string"),
        ("status: 17", "status must be a nonempty string"),
        ("date: 2026-02-29", "date must be an actual ISO date"),
        ("date: 2026-13-01", "date must be an actual ISO date"),
        ("date: '2026-1-01'", "date must be an actual ISO date"),
        ("date: 2026-10-29T12:00:00Z", "date must be an actual ISO date"),
        ("date: !!timestamp 2026-02-30", "invalid frontmatter"),
        ("supersedes: []", "supersedes must be a reference"),
        ("supersedes: [docs/previous.md, null]", "supersedes must be a reference"),
        ("supersedes: docs/missing.md", "tracked repo-relative file"),
        ("supersedes: /docs/previous.md", "tracked repo-relative file"),
        ("supersedes: ../outside.md", "tracked repo-relative file"),
        ("supersedes: file:///tmp/source.md", "tracked repo-relative file"),
        ("supersedes: https:///missing-host", "tracked repo-relative file"),
        ("last-reviewed: 2026-10-29", "review fields must travel together"),
        (
            "last-reviewed: 2026-10-29\nreview-every: 3mo\ninvalidated-by: []",
            "invalidated-by must be a nonempty list",
        ),
    ],
)
def test_rejects_bad_frontmatter(source: str, expected: str) -> None:
    assert any(expected in message for message in messages(source))


def test_filename_date_is_redundant_but_can_be_allowed() -> None:
    path = "docs/2026-10-29-note.md"
    assert messages("date: 2026-10-29", path=path) == [
        "date duplicates the dated filename; remove it"
    ]
    assert not messages("date: 2026-10-30", path=path)
    assert not messages("date: 2026-10-29", path=path, config="allow-filename-date: true")


def test_frontmatter_is_optional_and_body_is_not_yaml() -> None:
    problems = check_frontmatter(
        texts={
            RepoPath("docs/plain.md"): "# Plain\n\n---\nstatus: [not yaml\n",
            RepoPath("docs/bom.md"): "\ufeff---\nstatus: open\n---",  # Closing marker at EOF.
        },
        tracked=frozenset(),
        policy=parse_policy(),
    )
    assert not problems


def test_missing_closing_marker_and_field_line_numbers() -> None:
    path = RepoPath("docs/a.md")
    problems = check_frontmatter(
        texts={path: "---\nstatus: open\n"}, tracked=frozenset(), policy=parse_policy()
    )
    assert problems[0].line == 1
    assert problems[0].message == "frontmatter needs a closing --- line"
    problems = check_frontmatter(
        texts={path: "---\nstatus: open\n\ndate: bad\n---\n"},
        tracked=frozenset(),
        policy=parse_policy(),
    )
    assert problems[0].line == 4


POLICY = """\
fields:
  archived: date
  publication: string
  witnesses: string-list
  replacements: references
default-allowed: []
rules:
  - paths: [docs/plans/special.md]
    allowed: [status]
    values:
      status: [open]
  - paths: [docs/plans/*.md]
    allowed: [status, archived, publication, witnesses, replacements]
    values:
      status: [planned, archived]
"""


def test_custom_fields_permissions_and_statuses_are_configurable() -> None:
    assert not messages(
        "status: archived\narchived: 2026-10-29\npublication: Example\n"
        "witnesses: [One]\nreplacements: docs/previous.md",
        path="docs/plans/a.md",
        config=POLICY,
    )
    assert "status must be one of: planned, archived" in messages(
        "status: active", path="docs/plans/a.md", config=POLICY
    )
    assert any("not allowed here" in message for message in messages("status: open", config=POLICY))
    assert not messages("status: open", path="docs/plans/special.md", config=POLICY)
    assert messages("status: planned", path="docs/plans/special.md", config=POLICY)
    assert messages("archived: yesterday", path="docs/plans/a.md", config=POLICY)


@pytest.mark.parametrize(
    "source",
    [
        "",
        "[]",
        "fields: {}\nfields: {}",
        "fileds: {}",
        "fields: []",
        "fields: {status: date}",
        "fields: {my_field: string}",
        "fields: {custom: typo}",
        "default-allowed: [typo]",
        "default-allowed: null",
        "allow-filename-date: yes",
        "rules: {}",
        "rules: [null]",
        "rules: [{paths: ['docs/*.md']}]",
        "rules: [{paths: [], allowed: []}]",
        "rules: [{paths: ['/docs/*.md'], allowed: []}]",
        "rules: [{paths: ['../*.md'], allowed: []}]",
        "rules: [{paths: ['docs/*.md'], allowed: [], typo: true}]",
        "rules: [{paths: ['docs/*.md'], allowed: [date], values: {date: [open]}}]",
        "rules: [{paths: ['docs/*.md'], allowed: [status], values: {status: []}}]",
        "rules: [{paths: ['docs/*.md'], allowed: [status], values: {status: [true]}}]",
    ],
)
def test_config_mistakes_fail_instead_of_weakening_checks(source: str) -> None:
    with pytest.raises(ValueError):
        parse_policy(source)
