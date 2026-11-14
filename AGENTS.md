# kb-distillery — agent guide for the engine

This file is for coding agents working on this repository. Humans start at [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md); terms such as kit, digest tier and knowledge operation are explained in [docs/index.md](docs/index.md).

kb-distillery is the engine behind knowledge bases: it ingests raw sources, distills them into a linked wiki, lints that wiki against a schema, and serves it as a graph explorer and an optional private site. **This repo is the tooling only.** A knowledge base is its own folder and its own git repo (`~/knowledge/<id>/`, the bases dir is `$KB_DISTILLERY_HOME`; or any folder given as `--kb <path>`); the only kb tracked here is `examples/demo`. Each kb carries its own `AGENTS.md`, rendered by `distill init` from `src/kb_distillery/kits/<kit>/AGENTS.template.md`; that file, not this one, tells an agent how to work inside a kb.

This file is the core every turn on the engine needs. Details live in `src/kb_distillery/kits/base/defaults/docs/`: read the doc the **Doc router** names before you act.

## Folders

| Folder | Rule |
|---|---|
| `src/kb_distillery/` | The Python package (the `distill` CLI; `kbd` is a deprecated alias of `distill`). Packages import only from their own layer or below (cli/server, then services/publish, then the pipeline stages, then vault/llm/storage, then config): the contract is in `pyproject.toml` and `pixi run lint-imports` enforces it. |
| `src/kb_distillery/kits/` | Ontology kits (`base`, `research`): `kit.toml`, skills, hooks, docs, page templates and the `AGENTS.template.md` every new kb gets. |
| `web/` | The React app (built into `src/kb_distillery/_webapp/`, generated, gitignored). |
| `tests/` | pytest mirroring `src/`, plus fixtures and an end-to-end harness. Tests run on a fixture kb, never on a real one. |
| `examples/` | `demo/` (a small tracked kb) and `launchd/` (plist templates). |
| `scripts/` | Git and Claude hooks, launch scripts. |
| `docs/` | Public documentation. |

## Hard rules

1. **CI is the truth.** `.github/workflows/ci.yml` runs every gate on each pull request and each merge-queue group: `pixi run test` (it includes the privacy ratchet), `ruff`, `lint-skills`, `lint`, `lint-imports`, `okf-check`, `web-check`, `api-schema-check`, `flags-check`, the graph e2e and ui-principles checks, the wheel and worker builds; the one required check is `all-green`, and GitHub's merge queue merges only on green. `ship commit` runs ruff, `lint-imports` and the mirrored tests locally. All of these must pass; never skip a gate (`--skip-checks`), weaken or skip a test to get green. A failure that is not yours: say so and stop; do not work around it.
2. **Changes land by pull request.** Work on a branch, never push to `main`, open a PR (`CONTRIBUTING.md`); the commit subject is `<type>(<component>): …` under 72 characters. The project's own helper is `pixi run ship` (start, commit, pr, merge; it opens the PR and enqueues the merge; CI runs the gates): `src/kb_distillery/kits/base/defaults/docs/lifecycle.md`.
3. **Review gates the risky changes.** A schema or paradigm PR is labelled `hold` and merges only after a maintainer's approving review on its head sha; do not try to lift a hold yourself. Exception: while the owner's night window is open (`ship night`, expires on its own) nothing is held and CI (`all-green`) alone decides the merge.
4. **The engine never edits a kb.** No writes to `~/knowledge`, `wiki/`, `raw/` or `think/` from engine work. Knowledge changes happen inside the kb, through `distill ops`. A tooling PR never touches `wiki/`, `raw/` or `think/`; when one request needs both, ship the tooling PR first, then do the knowledge step in the kb; when the target is unclear, ask one short question. A schema change ships as a held PR with a migration: bump `SCHEMA_VERSION`, add `src/kb_distillery/migrations/NNNN_*.py`.
5. **No personal strings.** Names, emails, handles, local paths and site names come from configuration (`~/.config/kb-distillery/`, a kb's `kb.toml`, env), never from code, tests or docs; use `octocat`, `me@example.com`, `/Users/jdoe`. The privacy ratchet (`src/kb_distillery/lint/privacy.py`, terms from `$KB_PRIVACY_TERMS` or `~/.config/kb-distillery/privacy.toml`) fails on a new file that carries one.
6. **Every LLM call goes through `kb_distillery.llm`:** one `--backend subscription|api|batch` choice (`$KB_LLM_BACKEND`, default subscription), never a new `claude -p`, SDK or HTTP call (`tests/llm/test_llm.py` fails on one). A plan for an LLM feature has a short Billing section. CLI: `pixi run llm -- ask|submit|status|collect`.
7. **Code that writes pages links relatively:** `[Tensor rank](tensor-rank.md)`, built only by `kb_distillery.vault.links`; never wikilinks, never a path.
8. **Ship dark.** A feature that cannot land in one PR merges in small PRs behind a flag (`src/kb_distillery/kits/base/defaults/flags.toml`; `pixi run flags-gen` regenerates `web/src/flags/registry.gen.ts`). Release is flipping the flag, not deploying.
9. **Agents never deploy.** No `share -- deploy|rollback|snapshot`, no `KB_SHARE_AUTODEPLOY` above 0; deploys belong to the maintainer (`src/kb_distillery/kits/base/defaults/docs/publish.md`).
10. **Tests never call a real LLM or the network,** and read config from fixtures: set `KB_APP_CONFIG=/nonexistent/app.toml` and `KB_SHARE_AUTODEPLOY=0` for ship and test runs.
11. Read a skill's `SKILL.md` before running it. The skills a kb gets are the sources in `src/kb_distillery/kits/<kit>/skills/` (how to write one: `docs/guides/write-a-skill.md`).
12. One transactional workflow at a time; prefer targeted reads over scanning trees.

## Intent router — requests -> where to look

A request to fix, change or add engine tooling *is* the ask: make the change on a branch and open a PR. Read the doc or guide first.

| The request says… | Do | Lands as |
|---|---|---|
| "fix / change / add / improve …" the explorer, graph, ingest, CLI, a kit skill, lint, anything in tooling | `CONTRIBUTING.md`, then the doc the **Doc router** names | PR |
| "add an endpoint / router / API / SSE stream / backend test", "expose X over HTTP" | `src/kb_distillery/kits/base/defaults/docs/dev.md` (code layout) and the server tests under `tests/` | PR |
| "port / add a screen", "frontend", "component", "app shell" (the React app under `web/`) | `web/` and `pixi run web-check` | PR |
| "new note type / new field / lint should require …" | a **schema** change (rule 4) | held PR, bumps the schema version |
| "create a skill / new workflow" | `docs/guides/write-a-skill.md` | PR |
| "new kit / storage connector / publisher" | `docs/guides/write-a-kit.md`, `docs/guides/add-a-storage-connector.md`, `docs/guides/add-a-publisher.md` | PR |
| "share / publish the site", "deploy status", "rollback", "snapshot the site" | `src/kb_distillery/kits/base/defaults/docs/publish.md` (maintainer only for deploys; rule 9) | Worker version |

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
| change `distill init` / `distill doctor` or the kb template files | `src/kb_distillery/kits/base/defaults/docs/init.md` |
| touch `raw/` or `meta/corpus.tsv` handling: format folders, inbox, dispositions, naming | `src/kb_distillery/kits/base/defaults/docs/raw-and-corpus.md` |
| change how courses, series or books are digested | `src/kb_distillery/kits/base/defaults/docs/collections.md` |
| change the ingest/digest/distill CLIs or the skill ladder | `src/kb_distillery/kits/base/defaults/docs/workflows.md` |
| change think-note distillation | `src/kb_distillery/kits/base/defaults/docs/think.md` |
| change coherence warnings or semantic lint | `src/kb_distillery/kits/base/defaults/docs/semantic-lint.md` |
| change how PDF pages become a checked transcript: reader, parser, judge, auditor, `!` / `!!` marks, `meta/parsed/` | `src/kb_distillery/kits/base/defaults/docs/parse.md` |
| change how agent proposals are reviewed or applied | `src/kb_distillery/kits/base/defaults/docs/proposals.md` |
| write or change a skill | `docs/guides/write-a-skill.md` |
