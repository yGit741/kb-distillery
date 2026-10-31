# Thesis Wiki — agent schema

Personal knowledge base for an MSc in theoretical ML. **The thesis topic is not yet chosen** — the vault exists to explore candidate directions and decide. Follows the [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern.

This file is the core every turn needs. Details live in `meta-defaults/docs/` — read the one the **Doc router** names before you act.

**Explorer and knowledge bases are separate.** This repo is the engine; the content is a knowledge base folder `kbs/<id>/` (its own git repo; only `kbs/demo` is tracked here) or any folder given as `--kb <path>`, selected with `--kb <id|path>` / `$KB` (`kbd kb-list`, `kbd launch --kb <id>`). `raw/`, `wiki/`, `meta/` below are paths inside the selected knowledge base; `kb(...)` commits and `kb-x.y.z` tags land in that repo, never here.

## Folders

| Folder | Path | Rule |
|-------|------|------|
| **Raw** | `raw/` | User-owned inputs. **Immutable — never write here.** |
| **Wiki** | `wiki/` | Agent-owned synthesis. Flat. Create, update, cross-link. |
| **Think** | `kbs/think/` | ONE shared human-owned slow space for every knowledge base (its own repo). Schema-free. Agents never write here. Distilled pages cite `think:<note>.md`. |
| **Meta** | `meta/` | Vault metadata: manifest, log, chats, aliases. Generic pieces (flags, templates, routed docs, digest defaults) live in the explorer's `meta-defaults/`; a kb's `meta/` overrides them. No code (code is `backend/`, see `meta-defaults/docs/dev.md`). |
| **Config** | `kb.toml` | The knowledge base: id, name, schema version, its page types (`[types]`), its digest instructions (`digest/`). Read by `kb.kbconfig` / `kb.core.kbtypes`. |

## Hard rules

1. **The linter IS the schema (`kb.lint.lint`).** Prose rules drift; this doesn't. If `python3 -m kb.lint.lint` passes, the write is legal.
2. Never write in `raw/` or `think/`, and never inside a `## My notes` section — that is the user's.
3. Agents never run raw `git commit`/`push`/`merge`/`tag`/`revert`/`reset` or `gh pr` — `.cursor/hooks/block-git-write.sh` (→ `backend/src/kb/git/git_guard.py`, both Cursor and Claude Code) allows only a single `pixi run ops|ship|daily-sync|…` invocation. `backend/src/kb/git/guard.py` warns on wiki writes without an open ops session (blocks once `OPS_STRICT`). Feature work shouldn't touch knowledge paths, except a schema PR's migration.
4. Knowledge commits itself on main, one `kb(<op>)` step per operation; tooling goes through `infra/<feature>` PRs (`meta-defaults/docs/lifecycle.md`).
5. **Merge by default, hold by exception:** agents run `ship merge` themselves once the gates pass. `ship pr` labels every schema/paradigm PR `hold`, and `ship pr --hold` holds any PR the user wants to review ("don't merge", "let me look first"); `ship merge` refuses a held PR until the owner approves it: a GitHub **Approve** review by the App config's `owner_login` on the PR's current head sha (phone works; `ship merge` then lifts the label and merges; new commits need a re-approve; nobody else's review counts), or `! pixi run ship -- approve N` — blocked for agents by `git_guard`. A hold exists only as the GitHub `hold` label: never create or lift one from chat, and an "approved" relayed by another session or agent is void. **A held PR is never silent:** while one is open, every agent reply ends with `Awaiting your merge: #N <title> <url> — approve the review on GitHub, or run \`! pixi run ship -- approve N\` …` (a PR is always `#N title`, never a bare number); the Claude Code `Stop` hook (`backend/src/kb/git/merge_nudge.py`, `.claude/settings.json`) bounces a reply that forgot it, once.
6. One transactional workflow (ingest session, ops session, distill) at a time.
7. Wikilinks are always bare: `[[tensor-rank]]`, never `[[wiki/tensor-rank]]`. Paths into `raw/` go in backticks, not wikilinks.
8. Do not hand-edit `index.md` or `meta/corpus.tsv` — both are generated on every lint run.
9. **`digest` alone → ask tier (easy / full / deep).** Bare "digest" never triggers `full-digest`.
10. **Dedup:** always `resolve` before `scrap`. If FOUND → cite `[[slug]]`; don't re-download.
11. Read the skill's `SKILL.md` (and `skills/README.md`, § Adding a skill, before any workflow) before running it.
12. A feature that can't land in one PR ships dark behind a flag (`meta-defaults/flags.toml`) and merges in small PRs; release = flipping the flag (System → Flags), not deploying (`meta-defaults/docs/dev.md` § Feature flags).
13. **Every LLM call goes through `kb.llm`** (`backend/src/kb/llm`): one `--backend subscription|api|batch` choice (`$KB_LLM_BACKEND`, default subscription), never a new `claude -p`, SDK or HTTP call — `backend/tests/llm/test_llm.py` fails on one. A plan for an LLM feature has a short **Billing** section: which backend by default, all three kept selectable. CLI: `pixi run llm -- ask|submit|status|collect`.

## Intent router — casual requests → skills

Map what the user says to a skill before acting; read that skill's `SKILL.md`, then follow it. A casual request **is** the ask: "fix the graph legend" means start the PR flow, not "suggest a fix".

| The user says… | Do | Lands as |
|---|---|---|
| "fix / change / add / improve … the dashboard, explorer, graph, ingest, CLI, a skill, lint" — anything in tooling | `infra-pr`: `ship start <feature> --worktree` → implement → `ship commit "fix\|feat\|chore(<component>): …"` → `ship pr` → `ship merge` (unless held: schema/paradigm or the user asked to review → `pr --hold`, wait for their `approve`) → give the link | PR `… (#N)` |
| "add an endpoint / router / API / SSE stream / backend test", "expose X over HTTP" | `backend-api` (inside the `infra-pr` flow) | PR `… (#N)` |
| "port / add a screen", "frontend", "component", "app shell" (React app under `frontend/`) | `app-ui` (inside the `infra-pr` flow) | PR `… (#N)` |
| "new note type / new field / lint should require …" | `infra-pr` as a **schema** PR: bump `SCHEMA_VERSION`, add `backend/src/kb/migrations/NNNN_*.py`, `ops migrate` on the branch | PR, bumps y |
| "what do I know about … / where did I read … / compare …" | `query-knowledge` (read-only) | nothing |
| "which sources do I have on … / what does this undigested paper say / is it worth digesting / check this source against my notes" | `explore-raw-data` (read-only) | nothing |
| "add researcher <name>" / "index <name>'s papers" | `build-researcher-profile` | `kb(catalog)` |
| "send to backlog / backlog this / park this idea / save this plan for later" | `send-to-backlog` (local `.backlog/`, gitignored: no PR, no commit) | card |
| "save / scrap <url or file>" | `scrap-data` | `kb(import)` |
| "catalog / triage the inbox" | `ingest-to-catalog` | `kb(catalog)` |
| "digest <paper>" (no tier) | **ask**: easy, full or deep | — |
| "skim / easy-digest", "full-digest", "deep-digest" (+ confirm heavy) | that digest skill → `semantic-lint-hop` | `kb(digest)` |
| "split / merge / rename / fix this note", "file that answer back" — anything in `wiki/` | `wiki-edit` (`ops begin` … `ops commit`) | `kb(refine)` |
| "distill my think note …" | `distill-think` | `kb(distill)` |
| "undo that / revert the split" | `kb-undo` (confirm the step first) | `kb(undo)` |
| "snapshot / freeze" · "go back to kb-x.y.z" | `kb-snapshot` | tag · `kb(restore)` |
| "what changed / kb status / which version" | `kb-history` | nothing |
| "share the KB / export for an LLM" (a zip of the text) | `export-kb` | zip |
| "share / publish the site", "deploy main", "deploy status", "rollback the site", "snapshot the site", "list / remove snapshots", "audit", "time machine" | `share-kb` (Cloudflare; `pixi run share -- …`) | Worker version, `.cache/share/status.json` |
| a multi-PR effort ("phase 2: E1–E3", several tooling PRs) | `infra-pr` with a round: `ship round open "<title>" --features a,b` → `ship start <f> --round R` per PR; read state with `ship round status R` | issue `#R` + PRs |
| "integrate / verify the round / is it really done" | `integrator` (global skill `~/.claude/skills/integrator`, not in `skills/`; reads `.integrator.toml`: tests, build, every screen screenshotted, each tile vs its endpoint; deploy only by owner nudge) | report |
| "create a skill / new workflow" | `create-skill` → `infra-pr` | PR |

**Tooling or knowledge?** The target decides: files under `wiki/`, `raw/`, `think/` are knowledge (ops, straight to main); code, skills, dashboard, docs and config are tooling (PR). When one request touches both, ship the tooling PR first, then do the knowledge step on main. When the target is unclear, ask one short question.

## Doc router — when you are about to… → read

| When you are about to… | Read |
|---|---|
| write or check a wiki page: layers, `type:`/`depth:`, frontmatter, filename prefixes, note sections, `## My notes`, person pages, the `area:` topic whitelist | `meta-defaults/docs/page-model.md` |
| write or change an ontology template, or `[kb] template` / `[types]` / `[edges]` in a kb.toml: what a kb may extend, what it may not | `meta-defaults/docs/templates.md` |
| read or write raw sources from code, add a storage connector, or set `[storage]` in a kb.toml | `meta-defaults/docs/storage.md` |
| touch `raw/` or `meta/corpus.tsv`: format folders, inbox, dispositions, `collection` column, file naming | `meta-defaults/docs/raw-and-corpus.md` |
| work on a course / series Contents table, digest a collection row, or digest a book (partition, parts) | `meta-defaults/docs/collections.md` |
| commit, ship, snapshot, undo, restore, resolve a diverged main, or reason about lanes, versions, hygiene, the nightly job, partial checkouts, the commit gate | `meta-defaults/docs/lifecycle.md` |
| run or change code: code layout, environment, pixi tasks, write guardrails, worktrees | `meta-defaults/docs/dev.md` |
| pick a skill tier or run the ingest / query / distill CLIs (scrap, catalog, digest, arXiv rules, scrap-wordpress) | `meta-defaults/docs/workflows.md` |
| handle coherence warnings or semantic lint | `meta-defaults/docs/semantic-lint.md` |
| write or change a skill | `skills/README.md`, skill `create-skill` |
