# Developer guide

> Code layout, environment, pixi tasks, write guardrails, worktrees. Part of the doc router in [`AGENTS.md`](../../../../../../AGENTS.md).

## Code layout

Code, tools and the vault are separate top-level folders; `meta/` is vault metadata only.

```
src/kb_distillery/      Python app, package `kb_distillery` (src layout; `pyproject.toml` at the repo root)
  src/kb_distillery/cli/           `distill` (and `kbd`, deprecated): one front door to the commands below (see § distill and knowledge bases)
  src/kb_distillery/config/kb.py    kb discovery and selection: `~/knowledge/<id>` or `--kb <path>`, `kb.toml`
  src/kb_distillery/config/paths.py       the ONE vault-root resolver (the selected kb, else this checkout) + every data path constant
  src/kb_distillery/llm/           `kb_distillery.llm`: the one door to Claude (see § Billing)
  src/kb_distillery/vault/          schema, graph, hubs, scopes, persons, books, mathnorm, coherence, health
  src/kb_distillery/lint/          lint, lint_skills            src/kb_distillery/search/       query, semfind, explore_raw, citations
  src/kb_distillery/ingest|distill|ops (daily_sync, notify, report/)|publish/{site,cloudflare}/            src/kb_distillery/git/          guard, git_guard, commit_policy, ship, merge_nudge, curate_history
  src/kb_distillery/kits/          the kits: kit.toml, defaults/, skills (what a kb is given; `resource("kits")`)
  src/kb_distillery/migrations/    schema migrations (code); the applied ledger stays in meta/migrations/applied.tsv
  src/kb_distillery/services/      former dashboard *_data modules (graph, pages, corpus, scopes, chat, pipeline, lifecycle, ops)
  src/kb_distillery/server/           FastAPI app (`pixi run app`): routers/ auto-discovered, models/, sse.py, security.py; README.md = add-a-router recipe
  src/kb_distillery/llm/prompts/  chat prompts
  src/kb_distillery/publish/       publisher interface; site/ (build, snapshots, predicate, home, show, state); cloudflare/ (publisher, deploy, owner, ..., worker/ = the Cloudflare Worker (auth.js, admin.js, wrangler template) + its node tests)
tests/                  pytest, mirrored by package (tests/harness = the pipeline harness)
web/                    the React app (builds into src/kb_distillery/_webapp)
examples/               demo (the tracked sample kb), launchd
.claude/skills/         the engine's own dev skills (real files); the kb skills are src/kb_distillery/kits/<kit>/skills/
scripts/                githooks/, hooks/, qmd/, launch.sh
docs/                   public-roadmap.md: what shipped and what is next
~/knowledge/<id>/       one knowledge base each (its own git repo, outside this checkout); only examples/demo is tracked here; kbs/* stays gitignored as a guard
meta/                   VAULT METADATA ONLY: corpus.tsv, aliases.tsv, coherence-warnings.tsv, raw-renames.tsv,
                        chats/, templates/, migration/, migrations/applied.tsv, ops/sync.toml, thesis.md,
                        docs/ (the routed agent docs)
```

`pixi run api-schema` regenerates `web/src/api/schema.d.ts` from the API's OpenAPI (`api-schema-check` fails if stale).
Run a module with `python -m kb_distillery.<package>.<module>` (pixi tasks do; `src/` is on `PYTHONPATH`). Never `sys.path.insert`; take paths from `kb_distillery.config.paths`.

## distill and knowledge bases

**Read-only kbs.** `kb_distillery.config.kb.is_read_only(root)` is true for a kb under the engine's `examples/`, with `[kb] read_only = true`, or when `KB_READ_ONLY=1`. Every write path goes through `require_writable` (`ops.core` entry points, the `ops.wrap` writers, and the server's `require_writable_kb` dependency, 403 on mutating routes except app-state routes listed in `server/security.py`). New write paths call the same guard.

`distill <command> [args…]` (inside the repo: `pixi run distill --help`, or `python -m kb_distillery`; for a kb elsewhere see "`distill` on PATH" below) runs the module or script behind it, with the
rest of the command line passed through, so `--kb` goes after the command. The package `src/kb_distillery/cli/` imports
no kb code, so `--help` works with no knowledge base selected. `kbd` is the old name: it prints one deprecation line and
forwards (`cli/legacy.py` holds the mapping table; it goes after one release).

| Command | Was | What |
|---|---|---|
| `distill init` / `doctor` | `kbd init` / `doctor` | first kb from a template / check the environment and a kb |
| `distill kb list` / `kb show` | `kbd kb-list` / `kb-show` | every kb and where it is / the selected one, resolved |
| `distill kb open-example <name>` | | launch the app on `examples/<name>` with `KB_READ_ONLY=1` |
| `distill lint [--health]` | `kbd lint` / `health` | the schema is the linter |
| `distill launch` | `kbd launch` and `kbd app` | restart the app detached and open it (installed package: serve in the foreground) |
| `distill hooks install` / `hook <name>` | `kbd install-kb-hooks` | git + Claude Code hooks into a kb (hooks live in `src/kb_distillery/kits/base/hooks/`) / the stable entry the hooks call, failing closed |
| `distill ops …` / `ship …` | `kbd ops` / `ship` | knowledge operations / tooling PRs (`ship` only inside a checkout) |
| `distill ingest …` / `digest easy\|full\|deep\|many` | `pixi run ingest` | scrap, catalog and digest sources |
| `distill send <note> --to a,b` | `kbd distill` | send a think note into knowledge bases |
| `distill llm …` / `share …` / `propose …` | `pixi run llm` / `share` / graph.propose | the LLM door / the site / relation proposals |

Per-user files (API key, chat keys, usage ledger) live in `~/.config/kb-distillery/` (`config/userdir.py`). If only an
older per-user folder under `~/.config/` exists, every command but `doctor`/`hook`/`ship` prints the exact `mv` and exits 1: nothing is
moved for you.

**One discovery path.** A knowledge base is a folder with a `kb.toml`: `~/knowledge/<id>/` (the bases dir is
`$KB_DISTILLERY_HOME`, default `~/knowledge`; the folder name is the id; a checkout's own `kbs/` is not searched), or any folder given as `--kb <path>`. A `--kb` /
`$KB` value containing `/` or starting with `.` or `~` is a path, anything else an id. Selection: `--kb`, then `$KB`,
then the only kb there is. `$KB_ROOT` is internal (tools set it to hand a resolved folder to the processes they
start, e.g. the share build, qmd, the hooks); users never do. `$KB_BASES_DIR` replaces the bases dir for tests only.
`examples/demo` is the one kb tracked by this repo (a made-up job search, public); every other kb is its own git
repo and never enters this one. The hooks in a kb repo (`src/kb_distillery/kits/base/hooks/`, installed by `distill hooks install --kb <id|path>`) run `distill hook <name>` on `$PATH` with `$KB_ROOT` set to that repo; they never look for the engine and fail closed (exit 2) when `distill` is missing or cannot import. The git hooks follow the kit through `core.hooksPath`; the two Claude guards are copied into `.claude/hooks/`, so they update on `distill hooks install`. A kb whose `core.hooksPath` still names a retired hook folder of this repo has no hooks: run `distill hooks install --kb <id|path>`.

**`distill` on PATH, for a kb outside the repo.** The kb hooks (`distill hooks install`) call `distill hook …` and fail closed when it is missing, so a kb outside this checkout needs `distill` on `$PATH`. The pixi env deliberately holds no install of this package (a path dependency in `pixi.toml` was re-pointed at whichever worktree ran `pixi run`, breaking the shared env; `tests/test_pixi_env.py` guards it), so there is no `distill` script in `.pixi/`. Put a launcher on `$PATH` instead, e.g. `~/.local/bin/distill` (`chmod +x`):

```sh
#!/bin/sh
PYTHONPATH="<engine>/src" exec "<engine>/.pixi/envs/default/bin/python" -m kb_distillery "$@"
```

`<engine>` is the primary checkout (never a worktree: it is removed when the work merges). `distill init` and `distill hooks install` print this hint when `distill` is not on `$PATH`. A wheel (`pip install`) gets the same command from `pyproject.toml` (`distill = kb_distillery.cli:main`, `kbd = kb_distillery.cli:kbd_main`; keep both stable). Inside the repo, imports resolve per checkout through `[activation.env] PYTHONPATH` in `pixi.toml`, so a worktree always runs its own code; never run `pixi install`/`pixi add` from a worktree.

**Tags.** `pixi run ship -- tag <name> [--at REV] [--kb ID|PATH | --repo DIR]` puts an annotated tag on main of the
engine, a kb or any repo (local, never pushed; refuses `kb-*`, which are `ops snapshot`'s). `ship merge --local --pr N
--title "…" --no-push` merges without GitHub when there is no remote.

## Billing

Every LLM call goes through `kb_distillery.llm` (`pixi run llm -- ask|submit|status|collect`); a test fails on a new `claude -p`,
SDK or HTTP call elsewhere. One flag picks the backend per run: `--backend subscription|api|batch` or `$KB_LLM_BACKEND`.
**Default: `subscription`** (`claude -p`, the API-key variables scrubbed, so it runs on the login, not on credits).
`api` is the Messages API on `ANTHROPIC_API_KEY` (or `~/.config/kb-distillery/anthropic_key`); `batch` is the Message
Batches API (half price, asynchronous: `submit` then `collect`, a manifest under `.cache/llm/batches/`). All three stay
selectable on every run; a feature that calls an LLM says in its plan which backend it defaults to.

## Environment and tasks

**Environment:** one-time `curl -fsSL https://pixi.sh/install.sh | bash`, then restart the shell, then `pixi install` (again after any `pixi.toml` change — the Chat tab's agent backend needs the `claude-agent-sdk` PyPI package; behind a TLS-inspecting proxy run it with `SSL_CERT_FILE` pointing at a PEM of the keychain roots). All tasks below work via `pixi run <task>`.

```
pixi run lint                      check + reconcile + regenerate wiki/index.md and the wiki/<type>/index.md sections
pixi run health                    terminal health summary
pixi run launch                    restart dashboard from current code (detached) + open browser; also (re)starts the qmd search service when installed
pixi run qmd-install               (once) install the qmd search service in scripts/qmd (Node >= 22; models download on first start, ~1.9 GB under .cache/qmd/models)
pixi run qmd-serve                 run the qmd search service in the foreground (127.0.0.1:8766; KB_QMD_PORT to change)
pixi run qmd-cards                 rewrite .cache/qmd-cards/ (title + summary per page) — lint does this in the main checkout
pixi run vectors-build             our own copy of the card vectors → .cache/vectors.sqlite (same model as qmd; incremental)
pixi run vectors -- neighbours <slug>   pages closest in meaning (kb_distillery.search.vectors; also `status`)
pixi run summarize -- plan|run|show|judge|apply   Sonnet page summaries → .cache/summaries, Fable judge, apply inside an ops session
pixi run lint-strict               ingest-finalize checks
pixi run ingest-status             open ingest sessions
pixi run distill-propose -- <slug> propose graph brief from think page
pixi run distill-apply -- <slug>   apply distill plan to public KB
pixi run test                      the suite in parallel (`-n auto`, every test but the `serial` ones; a test fails after 120 s, pytest-timeout)
pixi run test-serial               the `serial` wall-clock tests alone (CI runs them in the shard that owns their dir)
pixi run ruff                      syntax errors and undefined names (ruff; [tool.ruff] in pyproject.toml)
pixi run test-e2e                  graph page mouse/keyboard scheme in headless Chromium (needs the playwright npm package)
pixi run test-ui-principles        every app screen, light + dark, against the [auto] ui-principles (see § PR gates)
pixi run lint-skills               validate every skills folder (each kit skills folder and .claude/skills)
pixi run export-kb                 zip wiki + think → .exported/ (LLM share)
pixi run share -- deploy-main      build main → private Cloudflare site (also: status, rollback, --dry-run)
pixi run install-deploy-owner      (user) install the launchd deploy owner — the only deployer; agents nudge it (`python -m kb_distillery.publish.cloudflare.owner nudge|once|status`)
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
pixi run install-hooks             use scripts/githooks (commit-msg, pre-commit, pre-push)
pixi run install-sync              install nightly daily-sync launchd job
```

**PR gates** are run by CI (`.github/workflows/ci.yml`: the `checks` job runs every lane check below on every PR, whatever it touches; `web` runs `web-check`; `all-green` fans them in). Locally the lane checks run only under `KB_SHIP_LOCAL_GATES=1` (`ship pr` / `ship merge`, by the lanes the branch touches vs origin/main; `src/kb_distillery/git/ship.py` `checks_for`): `web/` → `web-check` + `test-ui-principles`; `src/kb_distillery/server/` or `web/src/api` → `api-schema-check`; `web/src/features/graph/` or `tests/e2e/` → `test-e2e`; `meta/flags.toml` / `src/kb_distillery/config/flags/` → `flags-check`. A failing gate blocks the PR (in local-gates mode `--skip-checks "<reason>"` bypasses, reason in the PR body). `test-ui-principles` (`web/tests/ui-principles.test.mjs`) starts `kb_distillery.server` on a free port, loads each `.integrator.toml` screen plus `/think?note=…` at 1440×900 in light and dark, and fails on the `[auto]` rules of `~/.claude/skills/ui-principles/SKILL.md`: overlapping chrome (4), contrast (5), clipped text without ellipsis (9), colour literals added outside `web/src/theme/` (12), targets under 24×24 px (25), console errors and 4xx/5xx on load (30). Failures already present on main are listed in `web/tests/ui-principles.baseline.json` and only warn; that file must shrink, never grow — delete entries as screens are fixed (the test names the stale ones), and regenerate it with `UI_PRINCIPLES_WRITE_BASELINE=1` only on a branch that fixes screens. The `[eye]` rules stay with the `ui-review` skill. Both Playwright gates skip with a note when node or the playwright npm package is missing.

Without pixi, use `python3` equivalents (`python3 -m kb_distillery.lint.lint`, …).

**Write guardrails:** `src/kb_distillery/git/guard.py` blocks illegal agent writes via a PreToolUse hook in `.claude/settings.json` (Claude Code); the Bash git-write guard is `scripts/hooks/block-git-write.sh`. Claude Code also runs `src/kb_distillery/git/merge_nudge.py` on `Stop` (merge reminder; Cursor has no stop hook, so there the skill rule alone applies). `CLAUDE.md` imports this file for Claude instruction parity.

## Search service (qmd)

`scripts/qmd/server.mjs` is a long-running local Node service over [qmd](https://github.com/tobi/qmd): BM25 +
vector search (Qwen3-Embedding, multilingual) over one card per page — its title and `description:` line,
written to `.cache/qmd-cards/` by `kb_distillery.search.cards` (lint calls it in the main checkout; worktrees, CI and
share builds never touch the cards). The API's `/api/search` keeps its keyword hits and, with the runtime
flag `semantic-search` on, adds a `related` group from the service (`kb_distillery.search.qmd_client`, ≤ 1.5 s, at
most 3 per collection). The service answers 503 while it warms up or re-indexes, and the app then shows
keyword hits only; `mode=deep` adds qmd's LLM query expansion and re-ranking (seconds per query, not
used by the search box). Everything it stores is a cache under `.cache/qmd/`; delete it to rebuild.
`scripts/qmd/vectors.mjs` keeps our own copy of the same vectors in `.cache/vectors.sqlite` (qmd only answers
text queries); `kb_distillery.search.vectors` reads it for graph math — nearest pages, link closeness — never as evidence.

## Feature flags

`meta/flags.toml` is the one registry, read by the backend and (through codegen) the frontend. One `[[flag]]` table per flag: `name` (dotted, e.g. `screen.lifecycle`), `description`, `owner`, `created`, `expires` (TOML dates, `expires` after `created`), `kind`, `default`, `envs = { local, private, public }`.

- **Kinds:** `build` — fixed when a bundle is built; `runtime` — read at run time (server-side overrides come with the flags API).
- **Envs:** `local` is the app on this Mac (`python -m kb_distillery.server`, `web-dev`); `private` / `public` are the share builds (`VITE_SHARE_PROFILE`). `default` is used for an env the registry does not know (keep it on the safe side, off).
- **Backend:** `kb_distillery.config.flags.load()` validates (pydantic; `FlagError` lists every problem by flag) and `kb_distillery.config.flags.value(name, env)`.
- **Codegen:** `pixi run flags-gen` writes `web/src/flags/registry.gen.ts` (`FlagName` union, metadata, values per env) and the share route lists `web/src/routes/modules.share-{private,public}.ts` (core screens home/graph/pages + every `screen.<id>` build flag on in that env). `pixi run flags-check` fails on stale output; it runs in `web-check` and as a `ship` lane check for `meta/flags.toml` and `src/kb_distillery/config/flags/`. Never edit the generated files.
- **Frontend:** `flag(name)` from `@/flags`. A route in `routes/defs.ts` with `flag:` exists only where that flag is on. `setFlagOverrides()` is the runtime seam (runtime flags only).
- **Overrides (runtime flags only):** `GET /api/flags` (registry + effective value + `source` registry|override); `PUT /api/flags/{name}` `{value: bool|null}` writes `meta/.ops/flags.json` (gitignored) and needs header `X-KB-Owner-Token` = the macOS keychain item `kb-flags-owner` (created on first PUT; read it yourself with `security find-generic-password -s kb-flags-owner -w`). Agents are guard-blocked from the keychain, so only the owner flips flags; build flags → 409. The private site serves the same `GET /api/flags` from its Worker (KV `FLAGS_KV`, bound when the share config has `flags_kv_id`; PUT owner-email-only via the admin gate; unbound → `{}` / 503); public snapshots use built values. Frontend: `loadFlagOverrides()` at start, `useFlag(name)` re-renders on change.
- **Policy:** a feature that can't land in one PR ships dark behind a flag and merges in small PRs; release = flipping the flag (System → Flags), not deploying. A new flag needs an `owner` and `expires` at most 90 days after `created`.
- **Test matrix:** every flag needs a test for **both** states. pytest: `@pytest.mark.flag("name", True|False)` (`tests/conftest.py` forces it through `kb_distillery.config.flags.override`, all envs). vitest: `withFlag("name", true|false, fn)` from `@/flags/testing` (forces build flags too — a test-only seam; `routeDefsNow()` re-reads route flags). `python -m kb_distillery.config.flags.coverage` (in `flags-check` and `web-check`) scans `tests/**/test_*.py` and `web/src/**/*.test.ts(x)` and fails on a missing flag/state.
- **Expiry:** `lint` (`check_flags`) warns when a flag expires within 14 days and errors once it has expired or the registry is invalid; retire it with `meta/templates/flag-cleanup-pr.md` (`chore(flags): remove <name>`).
- **Not flags:** `apply_profile` in `kb_distillery/publish/site/build.py` (what data a public build strips) is privacy, not a feature switch, and stays on the profile.

## Performance

The graph snapshot is the expensive build (seconds on a 1,100-page kb), so it is cached and reused:

- **Graph snapshot:** `kb_distillery.graph.cache` keys it on the vault change signature (mtime and size of every wiki page and the side files it reads, plus git HEAD); an unchanged vault serves the cached build, concurrent callers share one build in flight. `KB_GRAPH_CACHE=0` turns the cache off (every call builds).
- **Health and ops:** `/api/health` and `/api/ops` reuse that same signature instead of a 60 s TTL, so they recompute after the vault changed; ops also keeps a 300 s backstop for state no file covers (open PRs) and recomputes on `refresh=1`.
- **Warm at start:** the server builds the snapshot in a daemon thread at start and a refresher re-checks the signature every `KB_GRAPH_WARM_INTERVAL` seconds (default 30), so the first request after idle is a hit. `KB_GRAPH_WARM=0` turns it off; tests and share builds never start it.
- **Frontend:** the app keeps query results for 5 minutes (`staleTime`), shares one graph query key across screens and prefetches the graph, so switching tabs does not refetch.

Measure with `pixi run perf -- --kb <path>` (`--idle N` sets the pause before the reopen round, `--no-browser` skips the Playwright tab passes, `--url` benches a running server). It starts a fresh server, times each endpoint cold, warm and after the idle pause, then times the tabs in a browser, and writes `.cache/perf/<stamp>.json` (`--out` renames it). Run it on a copy of the kb, never the real one, and note the machine load: a busy machine inflates every number.

Order of magnitude: on a 1,100-page kb, `/api/graph`, `/api/health` and `/api/ops` went from seconds to well under a second once warm; a cold first call still pays one build.

## Worktrees

`pixi run ship -- start <feature> --worktree` creates the worktree, symlinks the primary checkout's
`.pixi` env into it (`pixi.toml`'s `[activation.env]` `PYTHONPATH` makes `import kb` resolve to the
worktree's own source) and symlinks the gitignored `raw/` binaries so lint passes. Run code there as
`pixi run <task>` / `pixi run python -m kb_distillery.…` rather than a bare `python3`, which may not see the worktree's `kb_distillery`.

## Prebuilt web bundle

A release tag `v<version>` carries `webapp-<version>.tar.gz` and `.sha256` (built by `.github/workflows/web-bundle.yml`). When `src/kb_distillery/_webapp` is missing or stale, `distill launch` first calls `kb_distillery.webbuild.fetch_prebuilt` (sha256-checked, unpacked to a temp dir and renamed into place) and only builds `web/` locally when there is no bundle for this version, no network, or the bundle's `SOURCE_HASH` differs from the checkout's `web/` (a dev checkout keeps building). Force a local build with `KB_WEB_BUNDLE=0`; point at a fork's releases with `KB_WEB_BUNDLE_REPO=owner/name`. The checksum comes from the same release as the archive (it guards against corruption, not a tampered release), and the repo defaults to the checkout's origin.
