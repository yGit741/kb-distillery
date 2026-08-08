# Skill ladder

Canonical skills live here. Cursor copies via `pixi run sync-skills` → `.cursor/skills/`.

Read `meta/skills/<skill>/SKILL.md` before running a workflow.

## Token budgets

| Skill | LLM tier | Budget (in) | Runs without asking |
|-------|----------|-------------|---------------------|
| `scrap-data` | none | 0 | yes |
| `ingest-to-catalog` | none | 0 | yes |
| `easy-digest` | light | ~2–4k | only on `easy-digest` / `easy digest` / `skim` |
| `full-digest` | medium | ~8–12k | only on `full-digest` / `full digest` |
| `deep-digest` | heavy | ~25–40k+ | only on `deep-digest` + user confirms heavy |
| `query-kb` | light | ~3–15k | `query-kb`, `query kb`, `what do I know about` |
| `semantic-lint-hop` | light–medium | ~3–12k | after full/deep digest or distill apply |
| `lint-moc` | medium | ~8–20k | `lint-moc`, `lint moc` |

## Trigger rules

- **`digest` alone** → stop and ask (easy / full / deep). Never auto-pick full.
- **`full-digest`**, **`full digest`** → `full-digest` only. Bare "digest" does **not** trigger this.
- **`deep-digest`**, **`deep digest`** → confirm heavy tier, then `deep-digest`.
- **`easy-digest`**, **`easy digest`**, **`skim`** → `easy-digest`.

## Skills

| Skill | Purpose |
|-------|---------|
| [scrap-data](scrap-data/SKILL.md) | Save bytes to `raw/inbox/` (0 LLM) |
| [ingest-to-catalog](ingest-to-catalog/SKILL.md) | Route inbox → typed `raw/` + wiki stub (0 LLM) |
| [easy-digest](easy-digest/SKILL.md) | Abstract/metadata skim (light) |
| [full-digest](full-digest/SKILL.md) | Standard paper note, 25 pp extract (medium) |
| [deep-digest](deep-digest/SKILL.md) | Thesis-critical + neighbors (heavy, explicit only) |
| [distill-think](distill-think/SKILL.md) | Propose/apply from `think/` → transient `distilled-think-*` (medium) |
| [query-kb](query-kb/SKILL.md) | Answer from wiki — index-first, citations, optional file-back |
| [semantic-lint-hop](semantic-lint-hop/SKILL.md) | 1-hop review after ingest/distill — fix internal, note external on Connections |
| [lint-moc](lint-moc/SKILL.md) | On-demand theme MOC semantic pass |

## CLI

```bash
python3 -m meta.ingest resolve <url|arxiv|slug|title>  # check vault first (0 LLM)
python3 -m meta.ingest scrap <url|path> [--type articles|notes|slides|web|blog]
python3 -m meta.ingest catalog <inbox-path> [--course misc]
python3 -m meta.ingest drain-inbox [--course misc]
python3 -m meta.ingest easy-digest <slug|raw>
python3 -m meta.ingest full-digest <raw>    # begin→extract→map→draft→finalize
python3 -m meta.ingest deep-digest <raw> --confirm-heavy
python3 -m meta.distill propose <think-file> [--from bootstrap.md]
python3 -m meta.distill revise <think-file>
python3 -m meta.distill apply <think-file> [--cleanup]
python3 meta/query.py candidates "<keywords>"
python3 meta/query.py mocs
python3 meta/coherence.py status
python3 meta/semfind.py moc moc-info-theory
```

Legacy: `reingest-*` commands are bootstrap-only; prefer the skill ladder above.
