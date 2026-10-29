"""`doc-frontmatter`: optional, typed metadata with a configurable repository policy."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from agent_docs_hooks._repo import finish, normalize_root, read_text, repo_root, tracked_files
from agent_docs_hooks.frontmatter_policy import REVIEW_FIELDS, Policy, load_mapping, parse_policy
from agent_docs_hooks.problems import Problem, RepoPath


def _strings(value: object) -> list[str] | None:
    if isinstance(value, list) and value:
        strings = [item for item in value if isinstance(item, str) and item.strip()]
        if len(strings) == len(value):
            return strings
    return None


def _is_date(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _reference_problem(target: str, tracked: frozenset[RepoPath]) -> str | None:
    try:
        url = urlsplit(target)
    except ValueError:
        return f"reference {target!r} is malformed"
    if url.scheme in {"http", "https"} and url.netloc:
        return None
    path = PurePosixPath(target)
    if (
        url.scheme
        or url.netloc
        or url.query
        or url.fragment
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in target
        or RepoPath(str(path)) not in tracked
    ):
        return f"reference {target!r} must be an HTTP(S) URL or a tracked repo-relative file"
    return None


def check_frontmatter(
    *, texts: Mapping[RepoPath, str], tracked: frozenset[RepoPath], policy: Policy
) -> list[Problem]:
    """Check the supplied documents without reading files or changing metadata."""
    problems = []
    for path, text in texts.items():
        lines = text.removeprefix("\ufeff").splitlines()
        if not lines or lines[0].rstrip() != "---":
            continue
        try:
            end = next(index for index in range(1, len(lines)) if lines[index].rstrip() == "---")
        except StopIteration:
            problems.append(Problem(path, 1, "frontmatter needs a closing --- line"))
            continue
        try:
            fields, key_lines = load_mapping("\n".join(lines[1:end]))
        except ValueError as error:
            problems.append(Problem(path, 2, f"invalid frontmatter: {error}"))
            continue
        rule = policy.for_path(path)

        def report(
            key: str,
            message: str,
            document: RepoPath = path,
            positions: Mapping[str, int] = key_lines,
        ) -> None:
            problems.append(Problem(document, positions[key] + 1, message))

        for key, value in fields.items():
            if key not in rule.allowed:
                report(key, f"{key} is not allowed here; remove it or configure its purpose")
                continue
            kind = policy.fields[key]
            if kind == "string":
                if not isinstance(value, str) or not value.strip():
                    report(key, f"{key} must be a nonempty string")
                elif key in rule.values and value not in rule.values[key]:
                    report(key, f"{key} must be one of: {', '.join(rule.values[key])}")
            elif kind == "date":
                if not _is_date(value):
                    report(key, f"{key} must be an actual ISO date (YYYY-MM-DD)")
                elif (
                    key == "date"
                    and not policy.allow_filename_date
                    and value == PurePosixPath(path).name[:10]
                ):
                    report(key, "date duplicates the dated filename; remove it")
            elif kind == "string-list":
                if _strings(value) is None:
                    report(key, f"{key} must be a nonempty list of nonempty strings")
            elif kind == "references":
                targets = [value] if isinstance(value, str) and value.strip() else _strings(value)
                if targets is None:
                    report(key, f"{key} must be a reference or a nonempty list of references")
                else:
                    for target in targets:
                        if message := _reference_problem(target, tracked):
                            report(key, f"{key}: {message}")
        if fields.keys() & REVIEW_FIELDS and not fields.keys() >= REVIEW_FIELDS:
            missing = ", ".join(sorted(REVIEW_FIELDS - fields.keys()))
            problems.append(
                Problem(path, 2, f"review fields must travel together; missing {missing}")
            )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-docs-frontmatter", description="Check optional document frontmatter."
    )
    parser.add_argument("--docs-root", default="docs", type=normalize_root, metavar="DIR")
    parser.add_argument("--config", type=normalize_root, metavar="PATH")
    args = parser.parse_args(argv)
    root = repo_root()
    config_path = root / (args.config or ".frontmatter.yaml")
    try:
        if config_path.is_symlink():
            raise ValueError("configuration must be a regular file, not a symlink")
        if args.config or config_path.exists():
            policy = parse_policy(read_text(root, RepoPath(str(config_path.relative_to(root)))))
        else:
            policy = parse_policy()
    except (ValueError, OSError) as error:
        sys.stderr.write(f"{config_path.relative_to(root)}: {error}\n")
        return 2
    listing = tracked_files(root)
    texts = {
        path: read_text(root, path)
        for path in listing.files
        if path.startswith(f"{args.docs_root}/") and path.endswith(".md")
    }
    return finish(check_frontmatter(texts=texts, tracked=listing.files, policy=policy))
