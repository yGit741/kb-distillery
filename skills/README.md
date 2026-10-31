# Skill ladder

Canonical skills live here. `.claude/skills` and `.cursor/skills` are symlinks to this folder (`pixi run sync-skills` creates/verifies them after `pixi run lint-skills` passes) — edit here only, never in the mirrors.

Read `skills/<skill>/SKILL.md` before running a workflow.

## Token budgets

| Skill | LLM tier | Budget (in) | Runs without asking |
|-------|----------|-------------|---------------------|
| `scrap-data` | none | 0 | yes |
| `ingest-to-catalog` | none | 0 | yes |
| `export-kb` | none | 0 | `export-kb`, `export kb`, `share kb` |
| `easy-digest` | light (Haiku; ~5% Sonnet spot-check) | ~2–4k | only on `easy-digest` / `easy digest` / `skim` |
| `full-digest` | medium | ~8–12k | only on `full-digest` / `full digest` |
| `deep-digest` | heavy | ~25–40k+ | only on `deep-digest` + user confirms heavy |
| `distill-think` | medium | ~8–12k propose | `distill-think`, `distill think`, `graph brief` |
| `query-knowledge` | light | ~3–15k | `query-knowledge`, `query-kb`, `query kb`, `what do I know about` |
| `explore-raw-data` | light | ~2–6k | `explore-raw-data`, `explore raw`, `which sources do I have on …`, `is this paper worth digesting` |
| `semantic-lint-hop` | light–medium | ~3–12k | after full/deep digest or distill apply |
| `lint-moc` | medium | ~8–20k | `lint-moc`, `lint moc`, `lint topic` (topic audit) |
| `build-researcher-profile` | light | ~3–8k verify | `build researcher profile`, `index researcher` |
| `wiki-edit` | none | 0 | any free-form wiki edit (split, merge, rename, file-back) |
| `kb-history` | none | 0 | `kb history`, `kb status`, `what changed` |
| `kb-undo` | none | 0 | only when the user asks to undo a step |
| `kb-snapshot` | none | 0 | `snapshot`; restore only when the user asks |
| `infra-pr` | none | 0 | only when the user asks to ship / open / merge a PR |
| `app-ui` | none | 0 | `port the <screen>`, `add a screen`, `frontend`, `app shell` |
| `backend-api` | none | 0 | `add an endpoint`, `new router`, `change the API`, `api-schema` |
| `share-kb` | none | 0 | `share the site`, `publish`, `deploy main`, `rollback the site`, `deploy status` (not `export-kb`) |
| `guided-tour` | light | ~2–4k | `guided tour`, `walkthrough`, `onboarding tour` |
| `propose-relations` | light | ~1–2k per subject (batch) | `propose relations`, `relation proposals` (dry-run first; spends) |

## Trigger rules

- **`digest` alone** → stop and ask (easy / full / deep). Never auto-pick full.
- **`full-digest`**, **`full digest`** → `full-digest` only. Bare "digest" does **not** trigger this.
- **`deep-digest`**, **`deep digest`** → confirm heavy tier, then `deep-digest`.
- **`easy-digest`**, **`easy digest`**, **`skim`** → `easy-digest`.

## Skills

| Skill | Purpose |
|-------|---------|
| [export-kb](export-kb/SKILL.md) | Zip wiki + think for external LLM sharing (0 LLM) |
| [guided-tour](guided-tour/SKILL.md) | Spotlight guided tours over the real app (`?tour=<name>`), fixed Back / Next dock |
| [scrap-data](scrap-data/SKILL.md) | Save bytes to `raw/inbox/` (0 LLM) |
| [ingest-to-catalog](ingest-to-catalog/SKILL.md) | Route inbox → `raw/<format>/` + corpus `collection` (+ `paper-` Source page at depth listed) (0 LLM) |
| [easy-digest](easy-digest/SKILL.md) | Abstract/metadata skim → depth easy (light, Haiku) |
| [full-digest](full-digest/SKILL.md) | Full note with Key equations → depth full — paper, book part, or course/series row (medium) |
| [deep-digest](deep-digest/SKILL.md) | Thesis-critical + neighbors → depth deep (heavy, explicit only) |
| [distill-think](distill-think/SKILL.md) | Propose/apply from `think/` → transient `distilled-think-*` (medium) |
| [query-knowledge](query-knowledge/SKILL.md) | Answer from wiki — index-first, citations, optional file-back |
| [explore-raw-data](explore-raw-data/SKILL.md) | Look at cataloged raw sources (0 LLM CLI): find, read, check against pages, recommend a digest tier |
| [semantic-lint-hop](semantic-lint-hop/SKILL.md) | 1-hop review after ingest/distill — fix internal, note external on Connections |
| [lint-moc](lint-moc/SKILL.md) | Topic audit: on-demand semantic pass over one topic page (`theme-*`) |
| [build-researcher-profile](build-researcher-profile/SKILL.md) | Index full bib + catalog star papers only (light verify) |
| [propose-relations](propose-relations/SKILL.md) | Batch-LLM typed relation proposals between pages → `.cache/` only, per-subject review digest |

### Lifecycle skills (git history, versions, PRs)

Every knowledge operation is one commit on main: `kb(<op>): <summary> (kb-x.y.z)` — x paradigm, y schema, z step.
Writer CLIs (`kb.ingest`, `kb.distill`) commit themselves; free-form wiki edits go through `wiki-edit`.
Tooling is unversioned and ships as `infra/<feature>` PRs merged as `… (#N)`.

| Skill | Purpose |
|-------|---------|
| [wiki-edit](wiki-edit/SKILL.md) | Wrap free-form wiki edits in an ops session → one `kb(refine)` commit (0 LLM) |
| [kb-undo](kb-undo/SKILL.md) | Reverse one knowledge step as a new `kb(undo)` commit — wiki/ only (0 LLM) |
| [kb-snapshot](kb-snapshot/SKILL.md) | Tag `kb-x.y.z`, list snapshots, restore wiki/ to one (0 LLM) |
| [kb-history](kb-history/SKILL.md) | Version, steps, PRs, sessions — read-only (0 LLM) |
| [infra-pr](infra-pr/SKILL.md) | Ship tooling/schema via `infra/*` branch + PR, never squash (0 LLM, on request) |
| [share-kb](share-kb/SKILL.md) | Deploy main to the private Cloudflare site, status, rollback; snapshots later (0 LLM) |

### Meta skills

| Skill | Purpose |
|-------|---------|
| [create-skill](create-skill/SKILL.md) | Author new skills; runs through `lint-skills` gate (0 LLM) |
| [backend-api](backend-api/SKILL.md) | Add/change a FastAPI router, model, service and tests under `backend/`; regenerate `schema.d.ts` (0 LLM) |
| [app-ui](app-ui/SKILL.md) | Conventions for building screens in `frontend/` (tokens, palette, data-model words, porting checklist; 0 LLM) |

Template: [`SKILL_TEMPLATE.md`](SKILL_TEMPLATE.md) (not a skill; it has no `SKILL.md`).

## Adding a skill

1. **Extend vs new** — see [create-skill](create-skill/SKILL.md) decision tree.
2. Copy [`SKILL_TEMPLATE.md`](SKILL_TEMPLATE.md) → `skills/<name>/SKILL.md`.
3. Required: YAML `name` + `description` (with Use for / Do NOT), `## Triggers`, `## Do NOT`, `**LLM tier:**`, real CLI in `bash` blocks.
4. Register in this README (Token budgets row for ladder skills; Skills table always).
5. Update the Intent router in `AGENTS.md` if triggers change, and the Skill ladder in `meta-defaults/docs/workflows.md` if the ladder changes.
6. Gate:

```bash
pixi run lint-skills
pixi run sync-skills    # fails if lint-skills fails
```

**Vault guardrails** (any skill that touches data): `raw/` immutable (use CLI); `think/` human-only; open ingest session → no direct `wiki/` writes (`guard.py`); post-write → `python3 -m kb.lint.lint`.

**Every writing skill ends in one op commit.** Writer CLIs commit automatically (`--no-commit` to skip); any other wiki edit is wrapped in `pixi run ops -- begin …` / `pixi run ops -- commit` (see `wiki-edit`). Skills never run git writes themselves.

**Digest rule:** bare `digest` → ask tier; never auto-pick `full-digest`.

## CLI

```bash
python3 -m kb.ingest resolve <url|arxiv|slug|title>  # check vault first (0 LLM)
python3 -m kb.ingest scrap <url|path> [--type articles|notes|slides|web|blog]
python3 -m kb.ingest scrap-gdrive --dry-run
python3 -m kb.ingest scrap-wordpress <site> --prefix <collection short>   # whole WordPress.com blog → inbox
python3 -m kb.ingest scrap-mail <mbox-or-eml> [--slug thread-slug] [--force]
python3 -m kb.ingest catalog <inbox-path> [--collection <collection|person>] [--format <folder>] [--title T]
python3 -m kb.ingest drain-inbox [--collection <collection|person>]
python3 -m kb.ingest easy-digest <slug|raw>
python3 -m kb.ingest full-digest <raw>    # begin→extract→map→draft→finalize
python3 -m kb.ingest full-digest <collection-slug> --row N   # one course/series Contents row
python3 -m kb.ingest deep-digest <raw> --confirm-heavy
python3 -m kb.distill propose <think-file> [--from bootstrap.md]
python3 -m kb.distill revise <think-file>
python3 -m kb.distill apply <think-file> [--cleanup]
python3 -m kb.search.query candidates "<keywords>"
python3 -m kb.search.query mocs                    # topic pages (theme-*) as entry points
python3 -m kb.core.coherence status
python3 -m kb.search.semfind bundle --seeds wiki/foo.md --source manual
python3 -m kb.search.semfind topic theme-info-theory   # `theme` / `moc` aliases kept
python3 -m kb.maintenance.export
pixi run lint-skills
pixi run ops -- status
pixi run ops -- log --kb
pixi run ops -- snapshot "label"
pixi run ship -- status
pixi run share -- status
pixi run share -- deploy-main
```
