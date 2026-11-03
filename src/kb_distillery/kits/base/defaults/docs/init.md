# First run: `distill init` and `distill doctor`

A fresh clone becomes a working knowledge base and dashboard with no LLM:

```bash
pixi install
distill init            # asks for an id, name and kit when run in a terminal; --yes takes defaults
distill launch --kb <id>
```

## `distill init`

`distill init [--kb-id ID] [--name NAME] [--kit base|research] [--dir PATH] [--yes] [DIR]`

- Creates `<dir>/<id>/` (`--dir` defaults to the bases dir, `~/knowledge`, or `$KB_BASES_DIR`) as its **own git repository**:
  `kb.toml` (current `schema_version`, `[kb] kit`), `wiki/`, `raw/inbox/`, `meta/`, a minimal `.gitignore`, and one
  first commit `kb(import): create <id> from kit <k> (kb-x.y.0)` on `main`. The commit also carries the kit's files:
  `.claude/skills/` (copies of the kit's skills, parents from `extends` first), `.claude/docs/` (the docs `AGENTS.md`
  routes to), `.claude/hooks/` + `.claude/settings.json` (each hook runs `distill hook <name>`, no engine path),
  `AGENTS.md` (from `kits/<kit>/AGENTS.template.md`; a kit's template may put `{{parent}}` where its parent's goes) and
  `README.md`. After the rename `core.hooksPath` is set to the kit's git hooks (`distill hooks install`'s code).
- The folder is built in a hidden sibling and renamed into place, so a failure leaves nothing half made.
- Git code path: `kb_distillery.ops.core._git` / `_commit_paths` (the helpers `ops` commits with: no hooks, no lint, no push).
  `commit_policy` has no `init` op, so the commit uses `import`. Identity: your git config; if none, a local fallback
  author `kb-distillery <kb@localhost>` for that one commit.
- **Never overwrites.** It refuses an existing folder, the reserved ids `think` and `demo`, an id that is
  not lowercase letters, digits and dashes, and your home directory.
- Prompts only when stdin is a terminal and `--yes` is absent. Tests and scripts are non-interactive.
- Then it runs `distill doctor` on the new kb and prints the command to open it (`distill launch --kb <id>`, or the path when
  `--dir` is not the bases dir).
- **LLM is optional.** Init never asks for or stores a key. It prints one line: AI features stay off until a Claude
  subscription login (`claude login`) or an API key (`ANTHROPIC_API_KEY`, or `~/.config/kb-distillery/anthropic_key`) exists.

## `distill init --refresh`

`distill init --refresh [--kb ID|PATH]` re-syncs an existing kb with its kit (`[kb] kit`, or the older `template`): the skills
(the kit's files in each skill folder are overwritten; a skill folder the kit does not have is the kb's own and stays), `.claude/docs/`, the hooks,
`settings.json` (a changed one is first copied to `settings.json.bak`) and `core.hooksPath`. It prints one line per file added,
updated or removed, or `already up to date`, and is idempotent. It never touches `raw/`, `wiki/`, `meta/`, `think/`, `kb.toml`,
`README.md` or `AGENTS.md`: for `AGENTS.md` it only says whether it matches the kit template, differs (yours, left alone) or is
missing (never created). A file the kit no longer ships (a hook, or a file in a skill folder) is reported and left in place, never deleted. Nothing is committed: review, then
`distill ops chore hooks "refresh kit files"`.

## `distill doctor`

`distill doctor [--kb ID|PATH] [--json]`: PASS / WARN / FAIL / INFO with a one-line `fix:` each. Exit code 0 unless a FAIL.
Read-only: no network, no LLM call, no lint, nothing written.

| Check | FAIL when | WARN when |
|---|---|---|
| python, pixi env | python < 3.11 | not inside the pixi env |
| node | | missing (only the frontend build needs it) |
| git, identity | git missing | `user.name` / `user.email` unset |
| knowledge base | | none found (run `distill init`), or several and none selected |
| kb.toml | unreadable, schema version differs (`ops migrate`), template unknown | |
| kb folders | | `wiki/` or `meta/` missing |
| storage | connector cannot load | connector auth not ready |
| publisher | | configured one is broken (none configured is INFO) |
| llm subscription / api / batch | never | never (INFO: that backend stays off) |
| frontend | | `dist` not built and node or `node_modules` missing |

## `kb_distillery.llm.availability()`

`{backend: {ok, why, fix}}` for `subscription`, `api`, `batch`, with no LLM call. Subscription = the `claude` CLI is on
PATH and `claude auth status` says logged in with a subscription. api and batch = `api_key()` finds a key
(`ANTHROPIC_API_KEY`, then `~/.config/kb-distillery/anthropic_key`); the key itself is never reported. All three backends
stay selectable per run (`--backend`, `$KB_LLM_BACKEND`); the app uses this to grey out AI features when none is ok.
