"""`docs-indexed`: every doc is listed once in its directory's `INDEX.md`, and the root index is
linked from the root `CLAUDE.md` or `AGENTS.md`."""

from __future__ import annotations

import argparse
import posixpath
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.token import Token

from agent_docs_hooks._repo import finish, normalize_root, read_text, repo_root, tracked_files
from agent_docs_hooks.problems import Problem, RepoPath

INDEX = "INDEX.md"
ROOT_INSTRUCTIONS = (RepoPath("CLAUDE.md"), RepoPath("AGENTS.md"))
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:|//")


@dataclass(frozen=True, slots=True)
class Entry:
    """A valid index row: a trigger and the repo path its single link resolves to."""

    trigger: str
    target: RepoPath
    line: int


@dataclass(frozen=True, slots=True)
class BadRow:
    """A table row in an index that isn't a valid entry."""

    line: int
    reason: str


Row = Entry | BadRow


def index_inputs(*, tracked: frozenset[RepoPath], docs_root: str) -> frozenset[RepoPath]:
    """The files `check_index` reads: the tracked indexes it checks and the root instructions."""
    return frozenset(
        path
        for path in tracked
        if path in ROOT_INSTRUCTIONS or _index_dir(path, docs_root) is not None
    )


def _index_dir(path: str, docs_root: str) -> str | None:
    """The directory an index at `path` covers: the root's or a direct subdirectory's."""
    directory, name = posixpath.split(path)
    if name == INDEX and (directory == docs_root or posixpath.dirname(directory) == docs_root):
        return directory
    return None


def parse_rows(*, index_path: RepoPath, text: str) -> list[Row]:
    """Every body row of every table in an index, as an entry or the reason it isn't one."""
    base = posixpath.dirname(index_path)
    return [_row(cells, line=line, base=base) for line, cells in _table_rows(text)]


def _row(cells: list[Token], *, line: int, base: str) -> Row:
    if not cells or not cells[0].content.strip():
        return BadRow(line=line, reason="row has no trigger in its first cell")
    links = [] if len(cells) < 2 else _hrefs(cells[1])
    if not links:
        return BadRow(line=line, reason="row's second cell needs a link to a doc")
    if len(links) > 1:
        return BadRow(line=line, reason="row's second cell has more than one link")
    target = _resolve(links[0], base=base)
    if target is None:
        return BadRow(line=line, reason="row's link must point at a file in this repo, not a URL")
    return Entry(trigger=cells[0].content.strip(), target=target, line=line)


def _table_rows(text: str) -> Iterator[tuple[int, list[Token]]]:
    """Each table body row's 1-based line and the inline token of each of its cells."""
    in_body = False
    line = 0
    cells: list[Token] = []
    for token in _parser().parse(text):
        if token.type == "tbody_open":
            in_body = True
        elif token.type == "tbody_close":
            in_body = False
        elif in_body and token.type == "tr_open":
            line = (token.map or [0])[0] + 1
            cells = []
        elif in_body and token.type == "inline":
            cells.append(token)
        elif in_body and token.type == "tr_close":
            yield line, cells


def _parser() -> MarkdownIt:
    return MarkdownIt("commonmark").enable("table")


def _hrefs(inline: Token) -> list[str]:
    return [
        str(child.attrs["href"]) for child in inline.children or [] if child.type == "link_open"
    ]


def _resolve(href: str, *, base: str) -> RepoPath | None:
    """The repo path a link points at, without fragment or query; `None` for a URL or a bare
    fragment."""
    if _URL.match(href):
        return None
    path = unquote(href.split("#", 1)[0].split("?", 1)[0])
    if not path:
        return None
    joined = path.lstrip("/") if path.startswith("/") else posixpath.join(base, path)
    return RepoPath(posixpath.normpath(joined))


def check_index(
    *, tracked: frozenset[RepoPath], docs_root: str, texts: Mapping[RepoPath, str]
) -> list[Problem]:
    """Every problem with how the docs under `docs_root` are indexed and reached."""
    docs = sorted(
        path
        for path in tracked
        if path.startswith(f"{docs_root}/")
        and path.endswith(".md")
        and posixpath.basename(path) != INDEX
    )
    if not docs:
        return []
    root_index = RepoPath(f"{docs_root}/{INDEX}")
    problems: list[Problem] = []

    listable = []
    for doc in docs:
        if doc[len(docs_root) + 1 :].count("/") <= 1:
            listable.append(doc)
        else:
            problems.append(
                Problem(
                    path=doc,
                    line=None,
                    message=f"is too deep; docs go in {docs_root}/ or one directory below it",
                )
            )
    for directory in sorted({docs_root} | {posixpath.dirname(doc) for doc in listable}):
        index = RepoPath(f"{directory}/{INDEX}")
        if index not in tracked:
            problems.append(
                Problem(
                    path=index,
                    line=None,
                    message="is missing; a directory with docs needs an INDEX.md that lists them",
                )
            )

    indexes = sorted(path for path in tracked if _index_dir(path, docs_root) is not None)
    for index in indexes:
        directory = posixpath.dirname(index)
        expected = [doc for doc in listable if posixpath.dirname(doc) == directory]
        if index == root_index:
            expected += [path for path in indexes if path != root_index]
        problems += _check_one_index(
            index=index,
            rows=parse_rows(index_path=index, text=texts[index]),
            expected=expected,
            tracked=tracked,
            is_root=index == root_index,
        )

    if not any(root_index in _links(texts[path]) for path in ROOT_INSTRUCTIONS if path in texts):
        problems.append(
            Problem(
                path=root_index,
                line=None,
                message="isn't linked from the root CLAUDE.md or AGENTS.md",
            )
        )
    return problems


def _check_one_index(
    *,
    index: RepoPath,
    rows: Sequence[Row],
    expected: Sequence[RepoPath],
    tracked: frozenset[RepoPath],
    is_root: bool,
) -> list[Problem]:
    """Rules 4 to 6 for one index: valid rows, valid targets, and each expected path listed once."""
    directory = posixpath.dirname(index)
    problems = []
    first_line: dict[RepoPath, int] = {}
    for row in rows:
        if isinstance(row, BadRow):
            problems.append(Problem(path=index, line=row.line, message=row.reason))
            continue
        target = row.target
        mistake = _target_mistake(target, directory=directory, tracked=tracked, is_root=is_root)
        if mistake is not None:
            problems.append(Problem(path=index, line=row.line, message=mistake))
        elif target in first_line:
            problems.append(
                Problem(
                    path=index,
                    line=row.line,
                    message=f"{target} is already listed on line {first_line[target]}",
                )
            )
        else:
            first_line[target] = row.line
    problems += [
        Problem(path=path, line=None, message=f"isn't listed in {index}")
        for path in expected
        if path not in first_line
    ]
    return problems


def _target_mistake(
    target: RepoPath, *, directory: str, tracked: frozenset[RepoPath], is_root: bool
) -> str | None:
    """Why an entry's target isn't one this index may list, or `None` when it may."""
    if target not in tracked:
        return f"{target} doesn't exist or isn't tracked by git"
    target_dir, name = posixpath.split(target)
    if is_root and name == INDEX and posixpath.dirname(target_dir) == directory:
        return None
    if target_dir != directory:
        return f"{target} is in another directory; list it in that directory's {INDEX}"
    if not name.endswith(".md"):
        return f"{target} isn't a markdown file"
    if name == INDEX:
        return f"{target} is this index itself, not a doc"
    return None


def _links(text: str) -> set[RepoPath]:
    """The repo paths that the markdown links in a root file resolve to; code never counts."""
    targets = set()
    for token in _parser().parse(text):
        if token.type == "inline":
            for href in _hrefs(token):
                target = _resolve(href, base="")
                if target is not None:
                    targets.add(target)
    return targets


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-docs-indexed",
        description="Check that every doc is listed in its directory's INDEX.md.",
    )
    parser.add_argument("--docs-root", default="docs", type=normalize_root, metavar="DIR")
    args = parser.parse_args(argv)

    root = repo_root()
    tracked = tracked_files(root)
    texts = {
        path: read_text(root, path)
        for path in index_inputs(tracked=tracked, docs_root=args.docs_root)
    }
    return finish(check_index(tracked=tracked, docs_root=args.docs_root, texts=texts))
