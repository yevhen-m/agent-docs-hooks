from __future__ import annotations

import pytest
from factories import skill_md

from agent_docs_hooks.problems import Problem, RepoPath
from agent_docs_hooks.skills import check_skill, nearest_field, skill_subjects

PATH = RepoPath(".claude/skills/my-skill/SKILL.md")


def problems(text: str, *, path: RepoPath = PATH) -> list[Problem]:
    return check_skill(path=path, text=text)


def at(line: int | None, message: str, *, path: RepoPath = PATH) -> Problem:
    return Problem(path=path, line=line, message=message)


def test_valid_skill_passes() -> None:
    assert problems(skill_md()) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "# No frontmatter\n",
            at(None, "doesn't start with a frontmatter block between two --- lines"),
        ),
        (
            "---\nname: my-skill\n",
            at(None, "doesn't start with a frontmatter block between two --- lines"),
        ),
        (
            "---\nname: my-skill\ndescription: a: b\n---\n",
            at(3, "frontmatter isn't valid YAML: mapping values are not allowed here"),
        ),
        (
            "---\n- name\n- description\n---\n",
            at(None, "frontmatter must be key: value fields, not a list or a single value"),
        ),
    ],
)
def test_unreadable_frontmatter_is_the_only_problem(text: str, expected: Problem) -> None:
    assert problems(text) == [expected]


def test_crlf_frontmatter_is_read_after_decoding() -> None:
    from agent_docs_hooks._repo import decode_text

    assert problems(decode_text(skill_md().replace("\n", "\r\n").encode())) == []


@pytest.mark.parametrize("field", ["name", "description"])
def test_required_field_missing(field: str) -> None:
    text = skill_md(**{field: None})

    assert problems(text) == [at(None, f"{field} is missing")]


def named(name: str) -> list[Problem]:
    path = RepoPath(f".claude/skills/{name}/SKILL.md")
    return check_skill(path=path, text=skill_md(name=name))


def test_name_of_64_characters_passes() -> None:
    assert named("a" * 64) == []


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("a" * 65, "name is 65 characters; the limit is 64"),
        ("Bad_Name", "name must be lowercase letters and digits, with single hyphens between"),
        ("a--b", "name must be lowercase letters and digits, with single hyphens between"),
        ("claude-x", "name can't contain the reserved word claude"),
        ("my-anthropic-skill", "name can't contain the reserved word anthropic"),
    ],
)
def test_bad_name(name: str, message: str) -> None:
    path = RepoPath(f".claude/skills/{name}/SKILL.md")

    assert named(name) == [at(2, message, path=path)]


def test_name_differs_from_directory() -> None:
    path = RepoPath(".claude/skills/other/SKILL.md")

    assert problems(skill_md(), path=path) == [
        at(2, "name my-skill doesn't match its directory other", path=path)
    ]


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("x" * 1024, []),
        ("x" * 1025, [at(3, "description is 1,025 characters; the limit is 1,024")]),
        ('""', [at(3, "description is empty")]),
        ("Turns <x> into y", [at(3, "description can't contain < or >")]),
        ("No", []),
    ],
)
def test_description(description: str, expected: list[Problem]) -> None:
    assert problems(skill_md(description=description)) == expected


def test_when_to_use_with_angle_bracket_fails() -> None:
    assert problems(skill_md(when_to_use='"When a > b"')) == [
        at(4, "when_to_use can't contain < or >")
    ]


def test_argument_hint_may_use_angle_brackets() -> None:
    assert problems(skill_md(**{"argument-hint": '"<file>"'})) == []


@pytest.mark.parametrize(
    ("compatibility", "expected"),
    [
        ("x" * 500, []),
        ("x" * 501, [at(4, "compatibility is 501 characters; the limit is 500")]),
        ("42", [at(4, "compatibility must be a string")]),
    ],
)
def test_compatibility(compatibility: str, expected: list[Problem]) -> None:
    assert problems(skill_md(compatibility=compatibility)) == expected


@pytest.mark.parametrize("value", ['"false"', "yes"])
def test_user_invocable_must_be_a_boolean(value: str) -> None:
    assert problems(skill_md(**{"user-invocable": value})) == [
        at(4, "user-invocable must be true or false")
    ]


def test_non_string_name_fails() -> None:
    assert problems(skill_md(name="42")) == [at(2, "name must be a string")]


@pytest.mark.parametrize(
    ("key", "field"),
    [
        ("disable_model_invocation", "disable-model-invocation"),
        ("Description", "description"),
        ("descripton", "description"),
        ("user_invokable", "user-invocable"),
        ("when-to-use", "when_to_use"),
        ("mode", "model"),
        ("path", "paths"),
    ],
)
def test_typo_names_the_documented_field(key: str, field: str) -> None:
    assert problems(skill_md(**{key: "x"})) == [
        at(4, f"{key} isn't a documented field; did you mean {field}?")
    ]


@pytest.mark.parametrize("key", ["my-catalog-id", "x-owner", "date", "tools", "note"])
def test_other_custom_keys_pass(key: str) -> None:
    assert problems(skill_md(**{key: "x"})) == []
    assert nearest_field(key) is None


def test_all_documented_fields_pass() -> None:
    text = skill_md(
        when_to_use="When a file needs one thing",
        **{
            "argument-hint": '"<file>"',
            "arguments": "[file]",
            "disable-model-invocation": "false",
            "user-invocable": "true",
            "allowed-tools": "Read Grep",
            "disallowed-tools": "Bash",
            "model": "sonnet",
            "effort": "high",
            "context": "fork",
            "agent": "Explore",
            "background": "false",
            "hooks": "{}",
            "paths": '["src/**"]',
            "shell": "bash",
            "metadata": "{owner: me}",
            "license": "MIT",
            "compatibility": "Needs git",
        },
    )

    keys = {line.split(":", 1)[0] for line in text.split("---\n")[1].splitlines()}
    assert len(keys) == 20
    assert problems(text) == []


def test_skill_subjects_are_direct_children_only() -> None:
    tracked = frozenset(
        RepoPath(path)
        for path in (
            ".claude/skills/a/SKILL.md",
            ".claude/skills/a/nested/SKILL.md",
            ".claude/skills/SKILL.md",
            ".claude/skills/b/other.md",
            "elsewhere/c/SKILL.md",
        )
    )

    assert skill_subjects(tracked=tracked, skills_root=".claude/skills") == {
        ".claude/skills/a/SKILL.md"
    }
