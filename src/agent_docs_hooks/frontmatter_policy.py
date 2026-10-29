"""The generic document fields and the optional repository policy for `doc-frontmatter`."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node, ScalarNode

FIELD_TYPES = frozenset({"string", "date", "references", "string-list"})
GENERIC_FIELDS = {
    "status": "string",
    "date": "date",
    "supersedes": "references",
    "superseded-by": "references",
    "last-reviewed": "date",
    "review-every": "string",
    "invalidated-by": "string-list",
    "source-type": "string",
    "date-captured": "date",
    "origin": "string",
    "evidence-date": "date",
}
REVIEW_FIELDS = frozenset({"last-reviewed", "review-every", "invalidated-by"})


class _Loader(yaml.SafeLoader):
    """Reject duplicate/non-string keys, keep dates as strings, use YAML 1.2 booleans."""

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[object, object]:
        seen = set()
        for key, _ in node.value:
            if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                raise ConstructorError(None, None, "keys must be strings", key.start_mark)
            if key.value in seen:
                raise ConstructorError(None, None, f"duplicate key {key.value}", key.start_mark)
            seen.add(key.value)
        return super().construct_mapping(node, deep=deep)


_Loader.yaml_implicit_resolvers = {
    first: [
        (tag, pattern)
        for tag, pattern in resolvers
        if tag not in {"tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp"}
    ]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$", re.IGNORECASE), list("tTfF")
)


def load_mapping(text: str) -> tuple[Mapping[str, object], Mapping[str, int]]:
    """A safe YAML mapping and top-level key lines (one-based); raises ValueError on bad YAML."""
    loader = _Loader(text)
    try:
        node: Node | None = loader.get_single_node()
        if not isinstance(node, MappingNode):
            raise ValueError("expected a nonempty YAML mapping")
        fields = cast(dict[str, object], loader.construct_document(node))
        if not fields:
            raise ValueError("remove the empty frontmatter block")
        lines = {key.value: key.start_mark.line + 1 for key, _ in node.value}
        return fields, lines
    except yaml.YAMLError as error:
        raise ValueError(str(error)) from error
    finally:
        loader.dispose()


@dataclass(frozen=True, slots=True)
class Rule:
    paths: tuple[str, ...]
    allowed: frozenset[str]
    values: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class Policy:
    fields: Mapping[str, str]
    default_allowed: frozenset[str]
    rules: tuple[Rule, ...] = ()
    allow_filename_date: bool = False

    def for_path(self, path: str) -> Rule:
        """The first matching rule wins; patterns match repo-relative paths using fnmatch."""
        for rule in self.rules:
            if any(fnmatchcase(path, pattern) for pattern in rule.paths):
                return rule
        return Rule(paths=(), allowed=self.default_allowed, values={})


def _mapping(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{where} must be a mapping with string keys")
    return cast(dict[str, object], value)


def _strings(value: object, where: str, *, empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not empty):
        raise ValueError(f"{where} must be a {'possibly empty ' if empty else 'nonempty '}list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{where} must contain only nonempty strings")
    return tuple(cast(list[str], value))


def _keys(value: Mapping[str, object], allowed: set[str], where: str) -> None:
    unknown = value.keys() - allowed
    if unknown:
        raise ValueError(f"{where}: unknown setting(s): {', '.join(sorted(unknown))}")


def _allowed(value: object, fields: Mapping[str, str], where: str) -> frozenset[str]:
    names = frozenset(_strings(value, where, empty=True))
    if unknown := names - fields.keys():
        raise ValueError(f"{where}: undefined field(s): {', '.join(sorted(unknown))}")
    return names


def parse_policy(text: str | None = None) -> Policy:
    """Load strict repository configuration, or the generic policy when no file exists."""
    if text is None:
        return Policy(fields=dict(GENERIC_FIELDS), default_allowed=frozenset(GENERIC_FIELDS))
    config, _ = load_mapping(text)
    _keys(config, {"fields", "default-allowed", "rules", "allow-filename-date"}, "config")
    fields = dict(GENERIC_FIELDS)
    for name, kind in _mapping(config.get("fields", {}), "fields").items():
        if name in fields:
            raise ValueError(f"fields: {name} is already a generic field")
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name):
            raise ValueError(f"fields: {name!r} must use lowercase kebab-case")
        if not isinstance(kind, str) or kind not in FIELD_TYPES:
            raise ValueError(f"fields.{name}: choose one of {', '.join(sorted(FIELD_TYPES))}")
        fields[name] = kind
    default = _allowed(config.get("default-allowed", list(fields)), fields, "default-allowed")
    allow_filename_date = config.get("allow-filename-date", False)
    if not isinstance(allow_filename_date, bool):
        raise ValueError("allow-filename-date must be true or false")
    rule_values = config.get("rules", [])
    if not isinstance(rule_values, list):
        raise ValueError("rules must be a list")
    rules = []
    for index, item in enumerate(rule_values, 1):
        where = f"rule {index}"
        rule = _mapping(item, where)
        _keys(rule, {"paths", "allowed", "values"}, where)
        paths = _strings(rule.get("paths"), f"{where}.paths")
        for path in paths:
            if path.startswith("/") or ".." in path.split("/") or "\\" in path:
                raise ValueError(f"{where}.paths: use repo-relative POSIX patterns")
        allowed = _allowed(rule.get("allowed"), fields, f"{where}.allowed")
        values = {}
        for name, options in _mapping(rule.get("values", {}), f"{where}.values").items():
            if name not in allowed or fields[name] != "string":
                raise ValueError(f"{where}.values.{name}: must name an allowed string field")
            values[name] = _strings(options, f"{where}.values.{name}")
        rules.append(Rule(paths=paths, allowed=allowed, values=values))
    return Policy(
        fields=fields,
        default_allowed=default,
        rules=tuple(rules),
        allow_filename_date=allow_filename_date,
    )
