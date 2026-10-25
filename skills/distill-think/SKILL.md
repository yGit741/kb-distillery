---
name: distill-think
description: Distill think/ human notes into transient distilled-think pages + KB patches. Use for distill-think, distill think, graph brief. Do NOT edit think/ directly.
---

# Distill think

**LLM tier:** medium · **Budget:** ~8–12k tokens propose

Human deliberation lives in `think/` (schema-free, never agent-edited). Distill reads it and writes a review page `wiki/distilled-think-<name>.md` with `## Summary` and `## Proposed propagation`.

## Do NOT

- Edit `think/` directly — human-owned
- Skip `propose` before `apply`

## Triggers

- `distill-think`, `distill think`, `graph brief`
- Apply only on explicit user approval

## Rules

1. **Never edit `think/`** — blocked by `backend/src/kb/git/guard.py`.
2. **Propose first** — show Summary + proposal table; stop.
3. **Apply only when asked** — use `--cleanup` to delete the distilled page after propagate.

## Phase 1 — propose

```bash
python3 -m kb.distill propose my-true-research-start-here
python3 -m kb.distill propose my-file --from path/to/bootstrap.md   # one-time bootstrap
```

- Writes `meta/.distill/<id>/plan.json`.
- Writes `wiki/distilled-think-<name>.md` (review only).
- **No other wiki mutations.**

## Revise

```bash
python3 -m kb.distill revise my-true-research-start-here
```

Re-reads `think/`, rebuilds proposals, **keeps** an edited `## Summary` if you changed it on the distilled page.

## Phase 2 — apply

```bash
python3 -m kb.distill apply my-true-research-start-here
python3 -m kb.distill apply my-true-research-start-here --cleanup   # delete distilled page after
python3 -m kb.distill apply my-true-research-start-here --only 2,4
python3 -m kb.distill abort my-true-research-start-here
```

- Backs up targets, applies proposals, runs lint, rolls back on failure.
- Appends `meta/log.md`.
- Cite think paths as `` `think/...` `` in thread text — **not** `[[wikilinks]]` (think is outside wiki).

## Plan actions

| action | target |
|--------|--------|
| `append_threads` | topic page (`theme-*`) `## Threads` |
| `append_papers` | topic page (`theme-*`) `## Papers` |
| `update_section` | q-* section (e.g. Current state; `## Question` holds the formal statement — the H1 stays a short name ≤ 80 chars) |
| `append_related` | idea `related:` frontmatter |

## Agent constraints

- Direct writes to `think/` and `wiki/distilled-think-*.md` are blocked — use the CLI.

## Commit

The CLI commits this operation itself as `kb(distill): … (kb-x.y.z)` on main — only the files it changed (`--no-commit` to skip). Check with `pixi run ops -- log -n 1`. `apply` is the commit point; the distilled-think draft rides along.
