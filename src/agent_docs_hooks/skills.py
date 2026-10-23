"""`skills`: each `SKILL.md` has frontmatter that meets the Agent Skills spec and Claude Code."""

from __future__ import annotations

import argparse
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

import yaml

from agent_docs_hooks._repo import finish, normalize_root, read_text, repo_root, tracked_files
from agent_docs_hooks.problems import Problem, RepoPath

DOCUMENTED_FIELDS = frozenset(
    {
        "name",
        "description",
        "when_to_use",
        "argument-hint",
        "arguments",
        "disable-model-invocation",
        "user-invocable",
        "allowed-tools",
        "disallowed-tools",
        "model",
        "effort",
        "context",
        "agent",
        "background",
        "hooks",
        "paths",
        "shell",
        "metadata",
        "license",
        "compatibility",
    }
)
"""The frontmatter fields Claude Code documents at https://code.claude.com/docs/en/skills."""

RESERVED_WORDS = ("claude", "anthropic")
BOOLEAN_FIELDS = ("disable-model-invocation", "user-invocable", "background")
_NO_ANGLE_BRACKETS = ("name", "description", "when_to_use")
_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_NAME_LIMIT = 64
_DESCRIPTION_LIMIT = 1024
_COMPATIBILITY_LIMIT = 500
_FIRST_FRONTMATTER_LINE = 2
"""Line numbers count the opening `---` as line 1, so YAML's line 0 is the file's line 2."""


class _Yaml12Loader(yaml.SafeLoader):
    """PyYAML's safe loader with YAML 1.2 booleans: only true and false, so `yes`, `no`, `on` and
    `off` stay strings."""


_BOOL_TAG = "tag:yaml.org,2002:bool"
_Yaml12Loader.yaml_implicit_resolvers = {
    first: [(tag, pattern) for tag, pattern in resolvers if tag != _BOOL_TAG]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Yaml12Loader.add_implicit_resolver(
    _BOOL_TAG, re.compile(r"^(?:true|false)$", re.IGNORECASE), list("tTfF")
)


@dataclass(frozen=True, slots=True)
class _Frontmatter:
    fields: Mapping[str, object]
    lines: Mapping[str, int]


def skill_subjects(*, tracked: frozenset[RepoPath], skills_root: str) -> frozenset[RepoPath]:
    """Each tracked `<root>/<dir>/SKILL.md`; nested skills aren't discovered by Claude Code."""
    prefix = f"{skills_root}/"
    return frozenset(
        path
        for path in tracked
        if path.startswith(prefix) and PurePosixPath(path[len(prefix) :]).parts[1:] == ("SKILL.md",)
    )


def check_skill(*, path: RepoPath, text: str) -> list[Problem]:
    """Every frontmatter problem in one `SKILL.md`; an unreadable block is the only problem."""
    parsed = _parse_frontmatter(path=path, text=text)
    if isinstance(parsed, Problem):
        return [parsed]
    fields, lines = parsed.fields, parsed.lines

    def problem(key: str | None, message: str) -> Problem:
        return Problem(path=path, line=None if key is None else lines.get(key), message=message)

    problems = [
        problem(None, f"{key} is missing") for key in ("name", "description") if key not in fields
    ]
    for key in ("name", "description", "compatibility"):
        if key in fields and not isinstance(fields[key], str):
            problems.append(problem(key, f"{key} must be a string"))

    name = fields.get("name")
    if isinstance(name, str):
        problems.extend(
            problem("name", message)
            for message in _name_problems(name, directory=PurePosixPath(path).parent.name)
        )
    description = fields.get("description")
    if isinstance(description, str):
        if not description:
            problems.append(problem("description", "description is empty"))
        elif len(description) > _DESCRIPTION_LIMIT:
            problems.append(
                problem(
                    "description",
                    f"description is {len(description):,} characters; "
                    f"the limit is {_DESCRIPTION_LIMIT:,}",
                )
            )
    for key in _NO_ANGLE_BRACKETS:
        value = fields.get(key)
        if isinstance(value, str) and ("<" in value or ">" in value):
            problems.append(problem(key, f"{key} can't contain < or >"))
    compatibility = fields.get("compatibility")
    if isinstance(compatibility, str) and len(compatibility) > _COMPATIBILITY_LIMIT:
        problems.append(
            problem(
                "compatibility",
                f"compatibility is {len(compatibility)} characters; "
                f"the limit is {_COMPATIBILITY_LIMIT}",
            )
        )
    for key in BOOLEAN_FIELDS:
        if key in fields and not isinstance(fields[key], bool):
            problems.append(problem(key, f"{key} must be true or false"))
    for key in fields:
        field = None if key in DOCUMENTED_FIELDS else nearest_field(key)
        if field is not None:
            problems.append(problem(key, f"{key} isn't a documented field; did you mean {field}?"))
    return problems


def _name_problems(name: str, *, directory: str) -> list[str]:
    problems = []
    if not name:
        problems.append("name is empty")
    elif len(name) > _NAME_LIMIT:
        problems.append(f"name is {len(name)} characters; the limit is {_NAME_LIMIT}")
    if name and not _NAME_PATTERN.fullmatch(name):
        problems.append("name must be lowercase letters and digits, with single hyphens between")
    if name != directory:
        problems.append(f"name {name} doesn't match its directory {directory}")
    problems.extend(
        f"name can't contain the reserved word {word}"
        for word in RESERVED_WORDS
        if word in name.lower()
    )
    return problems


def nearest_field(key: str) -> str | None:
    """The documented field `key` equals or is one edit from, once both are lowercased and `_` is
    replaced by `-`; `None` when there is none."""
    wanted = _normal(key)
    matches = sorted(
        (0 if _normal(field) == wanted else 1, field)
        for field in DOCUMENTED_FIELDS
        if _within_one_edit(_normal(field), wanted)
    )
    return matches[0][1] if matches else None


def _normal(key: str) -> str:
    return key.lower().replace("_", "-")


def _within_one_edit(a: str, b: str) -> bool:
    """Whether one insertion, deletion or substitution, or none, turns `a` into `b`."""
    if len(a) > len(b):
        a, b = b, a
    if len(b) - len(a) > 1:
        return False
    for index, (left, right) in enumerate(zip(a, b, strict=False)):
        if left != right:
            skip = index if len(a) < len(b) else index + 1
            return a[skip:] == b[index + 1 :]
    return True


def _parse_frontmatter(*, path: RepoPath, text: str) -> _Frontmatter | Problem:
    """The block's fields and the line of each key, or the one problem that stops the read."""
    lines = text.split("\n")
    if lines[0] != "---" or "---" not in lines[1:]:
        return Problem(
            path=path,
            line=None,
            message="doesn't start with a frontmatter block between two --- lines",
        )
    loader = _Yaml12Loader("\n".join(lines[1 : lines.index("---", 1)]))
    try:
        node = loader.get_single_node()
        if not isinstance(node, yaml.MappingNode):
            return Problem(
                path=path,
                line=None,
                message="frontmatter must be key: value fields, not a list or a single value",
            )
        fields = loader.construct_document(node)
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark or error.context_mark
        return Problem(
            path=path,
            line=None if mark is None else mark.line + _FIRST_FRONTMATTER_LINE,
            message=f"frontmatter isn't valid YAML: {error.problem or error}",
        )
    except yaml.YAMLError as error:
        return Problem(path=path, line=None, message=f"frontmatter isn't valid YAML: {error}")
    finally:
        loader.dispose()
    key_lines = {
        key.value: key.start_mark.line + _FIRST_FRONTMATTER_LINE
        for key, _ in node.value
        if isinstance(key, yaml.ScalarNode) and key.tag == "tag:yaml.org,2002:str"
    }
    return _Frontmatter(
        fields={key: value for key, value in fields.items() if isinstance(key, str)},
        lines=key_lines,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-docs-skills",
        description="Check the frontmatter of every SKILL.md under the skills root.",
    )
    parser.add_argument(
        "--skills-root", default=".claude/skills", type=normalize_root, metavar="DIR"
    )
    args = parser.parse_args(argv)

    root = repo_root()
    subjects = skill_subjects(tracked=tracked_files(root), skills_root=args.skills_root)
    texts = {path: read_text(root, path) for path in subjects}
    return finish(
        [problem for path, text in texts.items() for problem in check_skill(path=path, text=text)]
    )
