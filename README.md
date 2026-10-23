# agent-docs-hooks

[pre-commit](https://pre-commit.com) hooks for the markdown that coding agents read: `CLAUDE.md`,
`AGENTS.md`, skills and your `docs/` folder.

When this markdown goes wrong, nothing tells you. A link to a doc you moved points at nothing. A doc
that nothing links to never gets read. A typo in a skill's frontmatter changes how the skill loads.
And a file that keeps growing costs context on every run, and agents follow it less. These hooks
catch all of that when you commit.

## What it checks

| Hook           | What it checks                                                                             |
| -------------- | ------------------------------------------------------------------------------------------ |
| `mdformat`     | Formats markdown with mdformat 1.0 and its GFM and frontmatter plugins, at 100 columns     |
| `doc-links`    | Every relative link and heading anchor points at something that exists                     |
| `doc-budget`   | Agent-facing files stay under their line and token limits                                  |
| `docs-indexed` | Every doc is listed in its folder's `INDEX.md`, and the root `CLAUDE.md` links the top one |
| `skills`       | Every skill's `SKILL.md` frontmatter follows the Agent Skills spec                         |

You don't need to install anything besides pre-commit. Each hook brings its own tools, including the
[lychee](https://github.com/lycheeverse/lychee) link checker.

## Install

Add this to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/yevhen-m/agent-docs-hooks
    rev: v0.1.0
    hooks:
      - id: doc-budget
      - id: docs-indexed
      - id: skills
      - id: doc-links
      - id: mdformat
```

Then run `pre-commit install` once. Pick only the hooks you want; each one works on its own.

A tag can be moved after you pin it. To pin the exact commit instead, run
`pre-commit autoupdate --freeze`.

These hooks are tested with pre-commit 4.6.2 on Linux and macOS. Windows isn't supported.

## The hooks

Every hook except `mdformat` checks all the files git tracks, not just the ones you're committing.
If you delete or rename a doc, the files that point at it break even though you never touched them,
and those are exactly the breaks worth catching.

The defaults fit a repo with docs in `docs/` and skills in `.claude/skills/`. If yours live
somewhere else, pass the paths as `args`. Paths are relative to the repo root.

```yaml
- id: doc-budget
  args: [--docs-root, documentation, --skills-root, agents/skills, --always-loaded, RULES.md]
- id: docs-indexed
  args: [--docs-root, documentation]
- id: skills
  args: [--skills-root, agents/skills]
```

### `mdformat`

Formats every markdown file you commit, at 100 columns, with numbered lists and LF line endings.
When it changes a file it prints `<path>: reformatted` and the commit stops. Look at the change, add
the file again and commit.

If your repo root has a `.mdformat.toml`, the hook passes none of its own options and your file's
settings win in full. Anything you don't set there falls back to mdformat's own defaults, not this
hook's, so wrapping and list numbering stop unless you set them. The GFM and frontmatter plugins
stay on either way. A `.mdformat.toml` in a subfolder, with none at the root, doesn't change
anything the hook sets, because its options override the file.

To skip some files, use pre-commit's `exclude:` on the hook. Don't use mdformat's own `exclude`
setting: mdformat 1.0.0 rejects it on Python older than 3.13.

### `doc-links`

Runs lychee offline over every markdown file git tracks. It checks links to files and folders and
links to headings (`#section`). It never fetches web links, so `http` and `https` links always pass.
A link that starts with `/` is read from the repo root, the way GitHub reads it.

To skip some links, put a `lychee.toml` in the repo root with regular expressions that match them.
For example, links into your home folder (`~/`) can't be checked on another machine:

```toml
exclude = ['/~/']
```

lychee reads the files on disk, so a file you haven't added to git yet still counts as a link
target.

### `doc-budget`

Files an agent loads on every run get the tight limit. Everything else gets the loose one.

| Files                                                           | Lines | Estimated tokens |
| --------------------------------------------------------------- | ----- | ---------------- |
| Any `CLAUDE.md` or `AGENTS.md`, and each `--always-loaded` path | 200   | 4,000            |
| Every other `.md` under the docs folder or the skills folder    | 500   | 5,000            |

Tokens are estimated as characters divided by 4, so you don't need an API key or a tokenizer. Other
markdown, such as your `README.md`, isn't checked.

Args: `--docs-root` (default `docs`), `--skills-root` (default `.claude/skills`), and
`--always-loaded PATH`, which you can repeat. Use `--always-loaded` for any other file your agent
loads on every run. If you name a file git doesn't track, the hook fails, so a typo can't slip by.

### `docs-indexed`

Every folder of docs needs an `INDEX.md` with a table. Each row says when to read a doc and links to
it:

```markdown
| When                            | Read                                 |
| ------------------------------- | ------------------------------------ |
| Before changing the billing API | [billing.md](billing.md)             |
| When a deploy fails             | [deploys/INDEX.md](deploys/INDEX.md) |
```

The rules:

1. Docs go in the docs folder or one folder below it, so indexes are at most two levels deep:
   `docs/INDEX.md` and `docs/<folder>/INDEX.md`.
2. Each `INDEX.md` lists every doc in its own folder exactly once. The top index also lists each
   subfolder's `INDEX.md` exactly once.
3. Every row of every table in an `INDEX.md` is an entry: some text in the first column, and a
   single link to a file in this repo in the second. Text and links outside tables are fine.
4. The root `CLAUDE.md` or `AGENTS.md` links to `docs/INDEX.md`. Claude Code reads only `CLAUDE.md`,
   so link it from there.

A doc is any `.md` file git tracks under the docs folder, other than `INDEX.md`. If there are no
docs, the hook passes.

Args: `--docs-root` (default `docs`).

### `skills`

Checks the frontmatter of each `<skills root>/<name>/SKILL.md`:

- It starts with a `---` block of `key: value` fields.
- `name` and `description` are both there.
- `name` is up to 64 lowercase letters, digits and single hyphens, matches its folder's name, and
  doesn't contain `claude` or `anthropic`.
- `description` is 1 to 1,024 characters.
- `name`, `description` and `when_to_use` don't contain `<` or `>`.
- `compatibility` is at most 500 characters.
- `disable-model-invocation`, `user-invocable` and `background` are `true` or `false`. Words like
  `yes` and `no` don't count.
- No key looks like a typo of a field
  [Claude Code documents](https://code.claude.com/docs/en/skills), such as `descripton` or
  `user_invocable`. Your own keys are fine unless they're one letter away from a real field, so a
  key named `mode` fails because it looks like `model`.

Skills nested deeper than one folder aren't checked, because Claude Code doesn't find them. A
symlinked skill folder isn't checked either.

Args: `--skills-root` (default `.claude/skills`).

## Why the formatter doesn't re-stage

Some formatter hooks run `git add` on the files they fix, so the commit goes through in one try.
This one doesn't, because that can lose your work.

Say you stage part of a file and keep editing the same lines without staging them. When you commit,
pre-commit sets your unstaged edits aside and runs the hooks on the staged version. If the formatter
then stages its fix, pre-commit can't put your edits back on top of it. The commit aborts with
"patch does not apply", and your edits are left only in a patch file under `~/.cache/pre-commit/`.
And `pre-commit run --all-files` doesn't set anything aside, so a re-staging formatter would also
stage edits you meant to leave out.

Without the `git add`, pre-commit handles the clash for you: it throws away the formatting, puts
your edits back, and the commit fails. Nothing is lost. The cost is one extra `git add` after the
formatter changes a file.

If a partly staged file keeps failing this way, format the whole file without pre-commit setting
anything aside, then stage the parts you want:

```sh
pre-commit run mdformat --files path/to/file.md
git add -p path/to/file.md
```

## What the hooks see

On `git commit`, pre-commit sets your unstaged edits aside first, so the hooks check what you're
committing. `pre-commit run --all-files` and `pre-commit run --files` don't, so they check the files
as they are on disk, unstaged edits included.
