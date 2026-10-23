"""Fresh input values for rule tests. Every factory takes keyword overrides only."""

from __future__ import annotations

from agent_docs_hooks.problems import Problem, RepoPath


def problem(*, path: str = "docs/a.md", line: int | None = None, message: str = "bad") -> Problem:
    return Problem(path=RepoPath(path), line=line, message=message)


def skill_md(**fields: str | None) -> str:
    """A `SKILL.md` whose frontmatter holds `name: my-skill`, a short description and `fields`.

    Values are YAML source, written as given; `None` leaves the field out. Keys keep their order,
    so `name` is on line 2 and `description` on line 3 unless overridden away."""
    merged: dict[str, str | None] = {"name": "my-skill", "description": "Does one thing."}
    merged.update(fields)
    body = "".join(f"{key}: {value}\n" for key, value in merged.items() if value is not None)
    return f"---\n{body}---\n\n# Skill\n"
