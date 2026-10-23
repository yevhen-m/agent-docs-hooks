"""`doc-budget`: agent-facing markdown stays within its line and estimated-token limits."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from agent_docs_hooks._repo import finish, normalize_root, read_text, repo_root, tracked_files
from agent_docs_hooks.problems import Problem, RepoPath, Skipped


@dataclass(frozen=True, slots=True)
class Measure:
    lines: int
    tokens: int


ALWAYS_LOADED = Measure(lines=200, tokens=4000)
"""For files an agent loads on every run: any `CLAUDE.md` or `AGENTS.md`, and `--always-loaded`."""

OTHER = Measure(lines=500, tokens=5000)
"""Every other markdown file under the docs root or the skills root."""

_ALWAYS_LOADED_NAMES = frozenset({"CLAUDE.md", "AGENTS.md"})


def budget_subjects(
    *,
    tracked: frozenset[RepoPath],
    docs_root: str,
    skills_root: str,
    always_loaded: frozenset[str],
) -> dict[RepoPath, Measure]:
    """Each tracked file the budget covers, with the limit that applies to it."""
    subjects = {}
    for path in tracked:
        if PurePosixPath(path).name in _ALWAYS_LOADED_NAMES or path in always_loaded:
            subjects[path] = ALWAYS_LOADED
        elif path.endswith(".md") and (_under(path, docs_root) or _under(path, skills_root)):
            subjects[path] = OTHER
    return subjects


def _under(path: str, root: str) -> bool:
    return path.startswith(f"{root}/")


_UNREADABLE_ALWAYS_LOADED = {
    None: "listed with --always-loaded but not tracked",
    Skipped.SYMLINK: (
        "listed with --always-loaded, but it's a symlink, which the hooks don't follow; "
        "list the file it points to instead"
    ),
    Skipped.DELETED: (
        "listed with --always-loaded and tracked by git, but missing from disk; "
        "restore it or drop the option"
    ),
}


def unreadable_always_loaded(
    *,
    tracked: frozenset[RepoPath],
    skipped: Mapping[RepoPath, Skipped],
    always_loaded: frozenset[str],
) -> list[Problem]:
    """A problem for each `--always-loaded` path the hook can't read, so a typo can't pass."""
    return [
        Problem(
            path=RepoPath(path),
            line=None,
            message=_UNREADABLE_ALWAYS_LOADED[skipped.get(RepoPath(path))],
        )
        for path in sorted(always_loaded - tracked)
    ]


def measure(text: str) -> Measure:
    """Lines, counting a last line without `\\n`, and tokens estimated as characters / 4."""
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return Measure(lines=lines, tokens=-(-len(text) // 4))


def check_budget(
    *, texts: Mapping[RepoPath, str], limits: Mapping[RepoPath, Measure]
) -> list[Problem]:
    """One problem per file over either of its limits, naming both measures and both limits."""
    problems = []
    for path, limit in limits.items():
        size = measure(texts[path])
        if size.lines > limit.lines or size.tokens > limit.tokens:
            message = (
                f"{size.lines:,} lines (limit {limit.lines:,}), "
                f"~{size.tokens:,} tokens (limit {limit.tokens:,})"
            )
            problems.append(Problem(path=path, line=None, message=message))
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-docs-budget",
        description="Check that agent-facing markdown stays within its line and token budget.",
    )
    parser.add_argument("--docs-root", default="docs", type=normalize_root, metavar="DIR")
    parser.add_argument(
        "--skills-root", default=".claude/skills", type=normalize_root, metavar="DIR"
    )
    parser.add_argument(
        "--always-loaded",
        action="append",
        default=[],
        type=normalize_root,
        metavar="PATH",
        help="a file the agent loads on every run; repeat for more",
    )
    args = parser.parse_args(argv)
    always_loaded: frozenset[str] = frozenset(args.always_loaded)

    root = repo_root()
    listing = tracked_files(root)
    limits = budget_subjects(
        tracked=listing.files,
        docs_root=args.docs_root,
        skills_root=args.skills_root,
        always_loaded=always_loaded,
    )
    texts = {path: read_text(root, path) for path in limits}
    return finish(
        [
            *unreadable_always_loaded(
                tracked=listing.files, skipped=listing.skipped, always_loaded=always_loaded
            ),
            *check_budget(texts=texts, limits=limits),
        ]
    )
