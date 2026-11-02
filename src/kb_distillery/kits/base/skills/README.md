# Base kit skills

The workflow skills every knowledge base gets from the `base` kit. A kb carries a copy in `.claude/skills/` (`distill init`); the source is `kits/base/skills/` in the engine. Read a skill's `SKILL.md` before running its workflow. How to write one: `docs/guides/write-a-skill.md` in the engine repo; the template is [`_TEMPLATE.md`](_TEMPLATE.md) (not a skill).

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
| `wiki-edit` | none | 0 | any free-form wiki edit (split, merge, rename, file-back) |
| `kb-history` | none | 0 | `kb history`, `kb status`, `what changed` |
| `kb-undo` | none | 0 | only when the user asks to undo a step |
| `kb-snapshot` | none | 0 | `snapshot`; restore only when the user asks |
| `propose-relations` | light | ~1–2k per subject (batch) | `propose relations`, `relation proposals` (dry-run first; spends) |

## Trigger rules

- **`digest` alone** → stop and ask (easy / full / deep). Never auto-pick full.
- **`full-digest`**, **`full digest`** → `full-digest` only. Bare "digest" does **not** trigger this.
- **`deep-digest`**, **`deep digest`** → confirm heavy tier, then `deep-digest`.
- **`easy-digest`**, **`easy digest`**, **`skim`** → `easy-digest`.

Every knowledge operation is one commit on main: `kb(<op>): <summary> (kb-x.y.z)` (x paradigm, y schema, z step). Writer CLIs
(`distill ingest`, `distill send`) commit themselves; free-form wiki edits go through `wiki-edit`.

## Skills

| Skill | Purpose |
|-------|---------|
| [export-kb](export-kb/SKILL.md) | Zip wiki + think for external LLM sharing (0 LLM) |
| [scrap-data](scrap-data/SKILL.md) | Save bytes to `raw/inbox/` (0 LLM) |
| [ingest-to-catalog](ingest-to-catalog/SKILL.md) | Route inbox → `raw/<format>/` + corpus `collection` (+ `paper-` Source page at depth listed) (0 LLM) |
| [easy-digest](easy-digest/SKILL.md) | Abstract/metadata skim → depth easy (light, Haiku) |
| [full-digest](full-digest/SKILL.md) | Full note with Key equations → depth full — paper, book part, or course/series row (medium) |
| [deep-digest](deep-digest/SKILL.md) | Deep read + neighbors → depth deep (heavy, explicit only) |
| [distill-think](distill-think/SKILL.md) | Propose/apply from `think/` → transient `distilled-think-*` (medium) |
| [query-knowledge](query-knowledge/SKILL.md) | Answer from wiki — index-first, citations, optional file-back |
| [explore-raw-data](explore-raw-data/SKILL.md) | Look at cataloged raw sources (0 LLM CLI): find, read, check against pages, recommend a digest tier |
| [semantic-lint-hop](semantic-lint-hop/SKILL.md) | 1-hop review after ingest/distill — fix internal, note external on Connections |
| [lint-moc](lint-moc/SKILL.md) | Topic audit: on-demand semantic pass over one topic page (`theme-*`) |
| [propose-relations](propose-relations/SKILL.md) | Batch-LLM typed relation proposals between pages → `.cache/` only, per-subject review digest |
| [wiki-edit](wiki-edit/SKILL.md) | Wrap free-form wiki edits in an ops session → one `kb(refine)` commit (0 LLM) |
| [kb-undo](kb-undo/SKILL.md) | Reverse one knowledge step as a new `kb(undo)` commit — wiki/ only (0 LLM) |
| [kb-snapshot](kb-snapshot/SKILL.md) | Tag `kb-x.y.z`, list snapshots, restore wiki/ to one (0 LLM) |
| [kb-history](kb-history/SKILL.md) | Version, steps, PRs, sessions — read-only (0 LLM) |
