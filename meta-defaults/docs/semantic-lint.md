# Semantic lint

> Structural vs semantic lint, warning kinds, coherence CLI. Part of the doc router in [`AGENTS.md`](../../AGENTS.md).

## Semantic lint

**Structural lint** (`src/kb_distillery/lint/lint.py`): links, schema, inbox — unchanged.

**Semantic lint** (`src/kb_distillery/core/coherence.py`): meaning-level checks, 0 LLM.

| kind | meaning | action |
|------|---------|--------|
| `internal` | bad ingestion — wiki stale/wrong vs source | **fix** (re-digest / edit); score ≥ 70 → lint ERROR |
| `external` | two digested sources disagree | **note** on each paper's `## Connections` / `## Links out` |
| `cosmetic` | graph hygiene | warn only |

```
python3 -m kb_distillery.core.coherence status
python3 -m kb_distillery.core.coherence fixed <id>    # internal resolved
python3 -m kb_distillery.core.coherence noted <id>    # external recorded on paper
python3 -m kb_distillery.core.coherence dismiss <id>
python3 -m kb_distillery.search.semfind topic theme-info-theory   # `theme` / `moc` kept as aliases
```

Manifest: `meta/coherence-warnings.tsv` (regenerated on lint; statuses persist).

After full/deep digest or distill apply: `SEMFIND_READY` → `skills/semantic-lint-hop/SKILL.md`. On-demand topic audit: `skills/lint-moc/SKILL.md`.
