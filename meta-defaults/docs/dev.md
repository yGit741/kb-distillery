# Developer guide

> Code layout, environment, pixi tasks, write guardrails, worktrees. Part of the doc router in [`AGENTS.md`](../../AGENTS.md).

## Code layout

Code, tools and the vault are separate top-level folders; `meta/` is vault metadata only.

```
backend/                Python app, package `kb` (src layout, pyproject.toml, editable install via pixi)
  src/kb/cli.py         `kbd`: one front door to the commands below (see § kbd and knowledge bases)
  src/kb/kbconfig.py    kb discovery and selection: `kbs/<id>` or `--kb <path>`, `kb.toml`
  src/kb/paths.py       the ONE vault-root resolver (the selected kb, else this checkout) + every data path constant
  src/kb/llm/           `kb.llm`: the one door to Claude (see § Billing)
  src/kb/core/          schema, graph, hubs, scopes, persons, books, mathnorm, coherence, health
  src/kb/lint/          lint, lint_skills            src/kb/search/       query, semfind, explore_raw, citations
  src/kb/ingest|distill|ops|report|share/            src/kb/git/          guard, git_guard, commit_policy, ship, merge_nudge, curate_history
  src/kb/maintenance/   daily_sync, notify, sync_skills, rename_raw, export, fix_math
  src/kb/migrations/    schema migrations (code); the applied ledger stays in meta/migrations/applied.tsv
  src/kb/services/      former dashboard *_data modules (graph, pages, corpus, scopes, chat, pipeline, lifecycle, ops)
  src/kb/api/           FastAPI app (`pixi run app`): routers/ auto-discovered, models/, sse.py, security.py; README.md = add-a-router recipe
  src/kb/dashboard/     legacy HTML pages + server until their screens are ported (served behind kb.api's catch-all)       src/kb/prompts/  chat prompts
  tests/                pytest, mirrored by package (tests/harness = the pipeline harness)
share/                  Cloudflare Worker (auth.js, admin.js, wrangler template) + its node tests
skills/                 agent skill sources (.claude/skills is a symlink to it)
tools/                  githooks/, kb-hooks/, launchd/, launch.sh
docs/                   ROADMAP.md: the migration to the open-source kb-distillery, phase by phase
kbs/                    knowledge bases: kbs/<id> is one kb (its own git repo); only kbs/demo is tracked here, the rest is gitignored
meta/                   VAULT METADATA ONLY: corpus.tsv, log.md, aliases.tsv, coherence-warnings.tsv, raw-renames.tsv,
                        chats/, templates/, migration/, migrations/applied.tsv, ops/sync.toml, thesis.md,
                        docs/ (the routed agent docs)
```

`pixi run api-schema` regenerates `frontend/src/api/schema.d.ts` from the API's OpenAPI (`api-schema-check` fails if stale).
Run a module with `python -m kb.<package>.<module>` (pixi tasks do); `kb` is installed editable, so `pixi install`
again after pulling this layout. Never `sys.path.insert`; take paths from `kb.paths`.

## kbd and knowledge bases

`kbd <command> [args…]` (pixi installs it; `pixi run kbd --help`) runs the module or script the matching
`pixi run <task>` runs, with the rest of the command line passed through, so `--kb` goes after the command.
It imports nothing from `kb`, so `--help` works with no knowledge base selected.

| Command | Same as | What |
|---|---|---|
| `kbd kb-list` / `kb-show` | `pixi run kb-list` / `kb-show` | every kb and where it is / the selected one, resolved |
| `kbd lint` / `health` | `pixi run lint` / `health` | the schema is the linter |
| `kbd app` | `pixi run app` | API + React shell (default port 8765) |
| `kbd launch` | `pixi run launch` | restart the app detached and open it |
| `kbd ship …` / `kbd ops …` | `pixi run ship` / `ops` | tooling PRs / knowledge operations |
| `kbd install-kb-hooks` | `pixi run install-kb-hooks` | git + Claude Code hooks into a kb |

**One discovery path.** A knowledge base is a folder with a `kb.toml`: `kbs/<id>/` in the main checkout (the folder
name is the id; a linked worktree uses the main checkout's `kbs/`), or any folder given as `--kb <path>`. A `--kb` /
`$KB` value containing `/` or starting with `.` or `~` is a path, anything else an id. Selection: `--kb`, then `$KB`,
then the only kb there is. `$KB_ROOT` is internal (tools set it to hand a resolved folder to the processes they
start, e.g. the share build, qmd, the hooks); users never do. `$KB_BASES_DIR` replaces `kbs/` for tests only.
`kbs/demo` is the one kb tracked by this repo (a made-up job search, public); every other `kbs/<id>` is its own git
repo and never enters this one. Hooks in a kb repo find the engine at `../..`; `KBD_DIR` overrides.

**Tags.** `pixi run ship -- tag <name> [--at REV] [--kb ID|PATH | --repo DIR]` puts an annotated tag on main of the
engine, a kb or any repo (local, never pushed; refuses `kb-*`, which are `ops snapshot`'s). `ship merge --local --pr N
--title "…" --no-push` merges without GitHub when there is no remote.

## Billing

Every LLM call goes through `kb.llm` (`pixi run llm -- ask|submit|status|collect`); a test fails on a new `claude -p`,
SDK or HTTP call elsewhere. One flag picks the backend per run: `--backend subscription|api|batch` or `$KB_LLM_BACKEND`.
**Default: `subscription`** (`claude -p`, the API-key variables scrubbed, so it runs on the login, not on credits).
`api` is the Messages API on `ANTHROPIC_API_KEY` (or `~/.config/thesis-kb/anthropic_key`); `batch` is the Message
Batches API (half price, asynchronous: `submit` then `collect`, a manifest under `.cache/llm/batches/`). All three stay
selectable on every run; a feature that calls an LLM says in its plan which backend it defaults to.

## Environment and tasks

**Environment:** one-time `curl -fsSL https://pixi.sh/install.sh | bash`, then restart the shell, then `pixi install` (again after any `pixi.toml` change — the Chat tab's agent backend needs the `claude-agent-sdk` PyPI package; behind a TLS-inspecting proxy run it with `SSL_CERT_FILE` pointing at a PEM of the keychain roots). All tasks below work via `pixi run <task>`.

```
pixi run lint                      check + reconcile + regenerate index.md
pixi run health                    terminal health summary
pixi run dashboard                 localhost health UI + graph explorer (http://127.0.0.1:8765, /graph, /digestion, /ops, /chat — a read-only research agent over the Claude Agent SDK, with the direct Messages call as fallback; pays with a stored API key (`~/.config/thesis-kb/keys/<name>`, switchable in the Session card) or, agent backend only, the `claude login` subscription)
pixi run launch                    restart dashboard from current code (detached) + open browser; also (re)starts the qmd search service when installed
pixi run qmd-install               (once) install the qmd search service in tools/qmd (Node >= 22; models download on first start, ~1.9 GB under .cache/qmd/models)
pixi run qmd-serve                 run the qmd search service in the foreground (127.0.0.1:8766; KB_QMD_PORT to change)
pixi run qmd-cards                 rewrite .cache/qmd-cards/ (title + summary per page) — lint does this in the main checkout
pixi run vectors-build             our own copy of the card vectors → .cache/vectors.sqlite (same model as qmd; incremental)
pixi run vectors -- neighbours <slug>   pages closest in meaning (kb.search.vectors; also `status`)
pixi run summarize -- plan|run|show|judge|apply   Sonnet page summaries → .cache/summaries, Fable judge, apply inside an ops session
pixi run lint-strict               ingest-finalize checks
pixi run ingest-status             open ingest sessions
pixi run distill-propose -- <slug> propose graph brief from think page
pixi run distill-apply -- <slug>   apply distill plan to public KB
pixi run test-e2e                  graph page mouse/keyboard scheme in headless Chromium (needs the playwright npm package)
pixi run test-ui-principles        every app screen, light + dark, against the [auto] ui-principles (see § PR gates)
pixi run lint-skills               validate skill definitions
pixi run sync-skills               create/verify the .claude/skills symlink (after lint-skills)
pixi run export-kb                 zip wiki + think → .exported/ (LLM share)
pixi run share -- deploy-main      build main → private Cloudflare site (also: status, rollback, --dry-run)
pixi run install-deploy-owner      (user) install the launchd deploy owner — the only deployer; agents nudge it (`python -m kb.share.owner nudge|once|status`)
                                   run it from your normal shell: it copies proxy CA/proxy env + PATH (no secrets) into the plist
pixi run share -- snapshot <name> <ref>   audit + publish a PUBLIC snapshot Worker (also: audit, list, history, remove, prune;
                                   `--replace` updates a sent snapshot at the same link, `rollback --worker <name>` undoes it)
pixi run lanes                     pending changes per lane + nightly sync, stale worktrees, open PRs
pixi run ops -- status             knowledge version, sessions, hooks (also: log, snapshot, undo, restore)
pixi run ops -- record <op> <target> "summary" <paths…>   commit already-modified knowledge as one op
pixi run ops -- sync --prefer local|origin [--root <checkout>]   diverged main: replay local kb steps on origin/main keeping one side's text in conflicts
pixi run ship -- prune [--apply]   delete merged infra/*, worktree-*, history/* branches + their clean worktrees
pixi run daily-sync                nightly: commit think/ edits + leftovers, push main + tags, then hygiene checks
pixi run hygiene                   git/ops hygiene report (stale worktrees, unpruned branches, unpushed steps, sessions, PRs, site, snapshots); --json
pixi run nightly-report            preview the nightly report mail (threads, findings, last 24 h); -- --html FILE / --json / --send; live at /ops in the dashboard
pixi run notify-test               send a one-line test email (Gmail app password from the keychain, see meta/ops/sync.toml)
pixi run ship -- start|commit|pr|merge   tooling via infra/<feature> PRs (on demand)
pixi run install-hooks             use tools/githooks (commit-msg, pre-commit, pre-push)
pixi run install-sync              install nightly daily-sync launchd job
```

**PR gates** (`ship pr` / `ship merge`, by the lanes the branch touches vs origin/main; `backend/src/kb/git/ship.py` `checks_for`): `frontend/` → `web-check` + `test-ui-principles`; `backend/src/kb/api/` or `frontend/src/api` → `api-schema-check`; `backend/src/kb/dashboard/`, `frontend/src/features/graph/` or `frontend/e2e/` → `test-e2e`; `meta/flags.toml` / `backend/src/kb/flags/` → `flags-check`. A failing gate blocks the PR (`--skip-checks "<reason>"` bypasses, reason in the PR body). `test-ui-principles` (`frontend/tests/ui-principles.test.mjs`) starts `kb.api` on a free port, loads each `.integrator.toml` screen plus `/think?note=…` at 1440×900 in light and dark, and fails on the `[auto]` rules of `~/.claude/skills/ui-principles/SKILL.md`: overlapping chrome (4), contrast (5), clipped text without ellipsis (9), colour literals added outside `frontend/src/theme/` (12), targets under 24×24 px (25), console errors and 4xx/5xx on load (30). Failures already present on main are listed in `frontend/tests/ui-principles.baseline.json` and only warn; that file must shrink, never grow — delete entries as screens are fixed (the test names the stale ones), and regenerate it with `UI_PRINCIPLES_WRITE_BASELINE=1` only on a branch that fixes screens. The `[eye]` rules stay with the `ui-review` skill. Both Playwright gates skip with a note when node or the playwright npm package is missing.

Without pixi, use `python3` equivalents (`python3 -m kb.lint.lint`, `python3 -m kb.dashboard`, …).

**Write guardrails:** `backend/src/kb/git/guard.py` blocks illegal agent writes via a PreToolUse hook in `.claude/settings.json` (Claude Code); the Bash git-write guard is `tools/hooks/block-git-write.sh`. Claude Code also runs `backend/src/kb/git/merge_nudge.py` on `Stop` (merge reminder; Cursor has no stop hook, so there the skill rule alone applies). `CLAUDE.md` imports this file for Claude instruction parity.

## Search service (qmd)

`tools/qmd/server.mjs` is a long-running local Node service over [qmd](https://github.com/tobi/qmd): BM25 +
vector search (Qwen3-Embedding, multilingual) over one card per page — its title and `summary:` line,
written to `.cache/qmd-cards/` by `kb.search.cards` (lint calls it in the main checkout; worktrees, CI and
share builds never touch the cards). The API's `/api/search` keeps its keyword hits and, with the runtime
flag `semantic-search` on, adds a `related` group from the service (`kb.search.qmd_client`, ≤ 1.5 s, at
most 3 per collection). The service answers 503 while it warms up or re-indexes, and the app then shows
keyword hits only; `mode=deep` adds qmd's LLM query expansion and re-ranking (seconds per query, not
used by the search box). Everything it stores is a cache under `.cache/qmd/`; delete it to rebuild.
`tools/qmd/vectors.mjs` keeps our own copy of the same vectors in `.cache/vectors.sqlite` (qmd only answers
text queries); `kb.search.vectors` reads it for graph math — nearest pages, link closeness — never as evidence.

## Feature flags

`meta/flags.toml` is the one registry, read by the backend and (through codegen) the frontend. One `[[flag]]` table per flag: `name` (dotted, e.g. `screen.lifecycle`), `description`, `owner`, `created`, `expires` (TOML dates, `expires` after `created`), `kind`, `default`, `envs = { local, private, public }`.

- **Kinds:** `build` — fixed when a bundle is built; `runtime` — read at run time (server-side overrides come with the flags API).
- **Envs:** `local` is the app on this Mac (`python -m kb.api`, `web-dev`); `private` / `public` are the share builds (`VITE_SHARE_PROFILE`). `default` is used for an env the registry does not know (keep it on the safe side, off).
- **Backend:** `kb.flags.load()` validates (pydantic; `FlagError` lists every problem by flag) and `kb.flags.value(name, env)`.
- **Codegen:** `pixi run flags-gen` writes `frontend/src/flags/registry.gen.ts` (`FlagName` union, metadata, values per env) and the share route lists `frontend/src/routes/modules.share-{private,public}.ts` (core screens home/graph/pages + every `screen.<id>` build flag on in that env). `pixi run flags-check` fails on stale output; it runs in `web-check` and as a `ship` lane check for `meta/flags.toml` and `backend/src/kb/flags/`. Never edit the generated files.
- **Frontend:** `flag(name)` from `@/flags`. A route in `routes/defs.ts` with `flag:` exists only where that flag is on. `setFlagOverrides()` is the runtime seam (runtime flags only).
- **Overrides (runtime flags only):** `GET /api/flags` (registry + effective value + `source` registry|override); `PUT /api/flags/{name}` `{value: bool|null}` writes `meta/.ops/flags.json` (gitignored) and needs header `X-KB-Owner-Token` = the macOS keychain item `kb-flags-owner` (created on first PUT; read it yourself with `security find-generic-password -s kb-flags-owner -w`). Agents are guard-blocked from the keychain, so only the owner flips flags; build flags → 409. The private site serves the same `GET /api/flags` from its Worker (KV `FLAGS_KV`, bound when the share config has `flags_kv_id`; PUT owner-email-only via the admin gate; unbound → `{}` / 503); public snapshots use built values. Frontend: `loadFlagOverrides()` at start, `useFlag(name)` re-renders on change.
- **Policy:** a feature that can't land in one PR ships dark behind a flag and merges in small PRs; release = flipping the flag (System → Flags), not deploying. A new flag needs an `owner` and `expires` at most 90 days after `created`.
- **Test matrix:** every flag needs a test for **both** states. pytest: `@pytest.mark.flag("name", True|False)` (`backend/tests/conftest.py` forces it through `kb.flags.override`, all envs). vitest: `withFlag("name", true|false, fn)` from `@/flags/testing` (forces build flags too — a test-only seam; `routeDefsNow()` re-reads route flags). `python -m kb.flags.coverage` (in `flags-check` and `web-check`) scans `backend/tests/**/test_*.py` and `frontend/src/**/*.test.ts(x)` and fails on a missing flag/state.
- **Expiry:** `lint` (`check_flags`) warns when a flag expires within 14 days and errors once it has expired or the registry is invalid; retire it with `meta/templates/flag-cleanup-pr.md` (`chore(flags): remove <name>`).
- **Not flags:** `apply_profile` in `kb/share/build.py` (what data a public build strips) is privacy, not a feature switch, and stays on the profile.

## Worktrees

`pixi run ship -- start <feature> --worktree` creates the worktree, symlinks the primary checkout's
`.pixi` env into it (`pixi.toml`'s `[activation.env]` `PYTHONPATH` makes `import kb` resolve to the
worktree's own source) and symlinks the gitignored `raw/` binaries so lint passes. Run code there as
`pixi run <task>` / `pixi run python -m kb.…` rather than a bare `python3`, which may not see the worktree's `kb`.
