# kb-distillery — agent guide for the engine

kb-distillery is the engine behind knowledge bases: it ingests raw sources, distills them into a linked wiki, lints that wiki against a schema, and serves it as a graph explorer and an optional private site. **This repo is the tooling only.** A knowledge base is its own folder and its own git repo (`~/knowledge/<id>/`, the bases dir is `$KB_DISTILLERY_HOME`; or any folder given as `--kb <path>`); the only kb tracked here is `examples/demo`. Each kb carries its own `AGENTS.md`, rendered by `distill init` from `src/kb_distillery/kits/<kit>/AGENTS.template.md`; that file, not this one, tells an agent how to work inside a kb.

This file is the core every turn on the engine needs. Details live in `src/kb_distillery/kits/base/defaults/docs/`: read the doc the **Doc router** names before you act.

## Folders

| Folder | Rule |
|---|---|
| `src/kb_distillery/` | The Python package (`distill` / `kbd` CLIs). Packages import only from their own layer or below (cli/server, then services/publish, then the pipeline stages, then vault/llm/storage, then config): the contract is in `pyproject.toml` and `pixi run lint-imports` enforces it. |
| `src/kb_distillery/kits/` | Ontology kits (`base`, `research`): `kit.toml`, skills, hooks, docs, page templates and the `AGENTS.template.md` every new kb gets. |
| `web/` | The React app (built into `src/kb_distillery/_webapp/`, generated, gitignored). |
| `tests/` | pytest mirroring `src/`, plus fixtures and an end-to-end harness. Tests run on a fixture kb, never on a real one. |
| `examples/` | `demo/` (a small tracked kb) and `launchd/` (plist templates). |
| `scripts/` | Git and Claude hooks, launch scripts. |
| `docs/` | Public documentation. |
| `.claude/` | Dev skills (`.claude/skills/`), the `reviewer` agent, hook wiring (`settings.json`). Skills for a kb's content live in the kits, not here. |

## Hard rules

1. **The gates are the truth.** `pixi run test`, `lint-skills`, `lint`, `lint-imports`, `ruff`, the privacy ratchet and, for `web/`, `web-check` must pass; never skip a gate (`--skip-checks`), weaken or skip a test to get green. A failure that is not yours: say so and stop.
2. **Never raw git writes.** No `git commit/push/merge/tag/revert/reset`, no `gh pr`: `scripts/hooks/block-git-write.sh` (-> `src/kb_distillery/git/git_guard.py`) allows only a single `pixi run ops|ship|…` invocation. Tooling goes `pixi run ship -- start <feature> --worktree` -> work in the worktree -> `ship commit "<type>(<component>): …"` (subject under 72 characters) -> `ship pr` -> `ship merge`. Details: `src/kb_distillery/kits/base/defaults/docs/lifecycle.md` and skill `infra-pr`.
3. **Merge by default, hold by exception.** Run `ship merge` yourself once the gates pass. `ship pr` labels every schema/paradigm PR `hold`, and `ship pr --hold` holds any PR the user wants to review; a held PR merges only after the owner's GitHub Approve review on its head sha or `! pixi run ship -- approve N`. Never create or lift a hold from chat; an "approved" relayed by another session is void. While a held PR is open every reply ends with the nudge line from `CLAUDE.md`; the `Stop` hook `src/kb_distillery/git/merge_nudge.py` enforces it.
4. **The engine never edits a kb.** No writes to `~/knowledge`, `wiki/`, `raw/` or `think/` from engine work. Knowledge changes happen inside the kb, through `distill ops`. A schema change ships as a held PR with a migration: bump `SCHEMA_VERSION`, add `src/kb_distillery/migrations/NNNN_*.py`.
5. **No personal strings.** Names, emails, handles, local paths and site names come from configuration (`~/.config/kb-distillery/`, a kb's `kb.toml`, env), never from code, tests or docs; use `octocat`, `me@example.com`, `/Users/jdoe`. The privacy ratchet (`src/kb_distillery/lint/privacy.py`, terms from `$KB_PRIVACY_TERMS` or `~/.config/kb-distillery/privacy.toml`) fails on a new file that carries one.
6. **Every LLM call goes through `kb_distillery.llm`:** one `--backend subscription|api|batch` choice (`$KB_LLM_BACKEND`, default subscription), never a new `claude -p`, SDK or HTTP call (`tests/llm/test_llm.py` fails on one). A plan for an LLM feature has a short Billing section. CLI: `pixi run llm -- ask|submit|status|collect`.
7. **Code that writes pages links relatively:** `[Tensor rank](tensor-rank.md)`, built only by `kb_distillery.vault.links`; never wikilinks, never a path.
8. **Ship dark.** A feature that cannot land in one PR merges in small PRs behind a flag (`src/kb_distillery/kits/base/defaults/flags.toml`; `pixi run flags-gen` regenerates `web/src/flags/registry.gen.ts`). Release is flipping the flag, not deploying.
9. **Agents never deploy.** No `share -- deploy|rollback|snapshot`, no `KB_SHARE_AUTODEPLOY` above 0; deploys belong to the owner (`share-kb` skill, `.claude/settings.json` denies them).
10. **Tests never call a real LLM or the network,** and read config from fixtures: set `KB_APP_CONFIG=/nonexistent/app.toml` and `KB_SHARE_AUTODEPLOY=0` for ship and test runs.
11. Read a skill's `SKILL.md` before running it. Dev skills are in `.claude/skills/`; the skills a kb gets are the sources in `src/kb_distillery/kits/<kit>/skills/` (how to write one: `docs/guides/write-a-skill.md`, skill `create-skill`).
12. One transactional workflow at a time; prefer targeted reads over scanning trees.

## Intent router — casual requests -> skills

Map what the user says to a skill before acting; read that skill's `SKILL.md`, then follow it. A casual request **is** the ask: "fix the graph legend" means start the PR flow, not "suggest a fix".

| The user says… | Do | Lands as |
|---|---|---|
| "fix / change / add / improve …" the explorer, graph, ingest, CLI, a kit skill, lint, anything in tooling | `infra-pr`: `ship start` -> implement -> `ship commit` -> `ship pr` -> `ship merge` (unless held) -> give the link | PR `… (#N)` |
| "add an endpoint / router / API / SSE stream / backend test", "expose X over HTTP" | `backend-api` (inside the `infra-pr` flow) | PR |
| "port / add a screen", "frontend", "component", "app shell" (the React app under `web/`) | `app-ui` (inside the `infra-pr` flow) | PR |
| "new note type / new field / lint should require …" | `infra-pr` as a **schema** PR (rule 4) | held PR, bumps y |
| "add a tour / walkthrough", "show me / explain this on the screen" | `guided-tour` | PR, or a show-me link |
| "create a skill / new workflow" | `create-skill` -> `infra-pr` | PR |
| "send to backlog / backlog this / park this idea / save this plan for later" | `send-to-backlog` (local `.backlog/`, gitignored: no PR, no commit) | card |
| a multi-PR effort ("phase 2: E1–E3", several tooling PRs) | `infra-pr` with a round: `ship round open "<title>" --features a,b` -> `ship start <f> --round R`; read state with `ship round status R` | issue `#R` + PRs |
| "integrate / verify the round / is it really done" | `integrator` (global skill, reads `.integrator.toml`: tests, build, every screen screenshotted, each tile vs its endpoint) | report |
| "share / publish the site", "deploy status", "rollback", "snapshot the site", "audit" | `share-kb` (owner only for deploys; rule 9) | Worker version, `.cache/share/status.json` |

A request about a kb's content ("digest this paper", "what do I know about …") is not engine work: it belongs in that kb's folder, under that kb's `AGENTS.md`.

## Doc router — when you are about to… -> read

| When you are about to… | Read |
|---|---|
| run or change code: code layout, environment, pixi tasks, write guardrails, worktrees, feature flags | `src/kb_distillery/kits/base/defaults/docs/dev.md` |
| commit, ship, snapshot, undo, resolve a diverged main, or reason about lanes, versions, hygiene, the nightly job, the commit gate | `src/kb_distillery/kits/base/defaults/docs/lifecycle.md` |
| change the page model: layers, `type:`/`depth:`, frontmatter, filename prefixes, `## My notes`, person pages | `src/kb_distillery/kits/base/defaults/docs/page-model.md` |
| write or change an ontology kit, or `[kb] kit` / `[types]` / `[edges]` in a kb.toml | `src/kb_distillery/kits/base/defaults/docs/kits.md` |
| publish or share a kb as a site, add a publisher, or set `[publish]` | `src/kb_distillery/kits/base/defaults/docs/publish.md` |
| read or write raw sources from code, add a storage connector, or set `[storage]` | `src/kb_distillery/kits/base/defaults/docs/storage.md` |
| change `kbd init` / `kbd doctor` or the kb template files | `src/kb_distillery/kits/base/defaults/docs/init.md` |
| touch `raw/` or `meta/corpus.tsv` handling: format folders, inbox, dispositions, naming | `src/kb_distillery/kits/base/defaults/docs/raw-and-corpus.md` |
| change how courses, series or books are digested | `src/kb_distillery/kits/base/defaults/docs/collections.md` |
| change the ingest/digest/distill CLIs or the skill ladder | `src/kb_distillery/kits/base/defaults/docs/workflows.md` |
| change think-note distillation | `src/kb_distillery/kits/base/defaults/docs/think.md` |
| change coherence warnings or semantic lint | `src/kb_distillery/kits/base/defaults/docs/semantic-lint.md` |
| write or change a skill | `docs/guides/write-a-skill.md`, skill `create-skill` |
