---
name: deep-digest
description: Thesis-critical deep digest with neighbor links (~25-40k+ tokens, HEAVY). Use ONLY when user explicitly says "deep-digest" or "deep digest" AND confirms heavy tier. Never auto-trigger.
---

# deep-digest

**LLM tier:** heavy · **Budget:** ~25–40k+ tokens in

**Requires explicit user permission** — nothing in this vault should run heavy without it.

## Triggers

- `deep-digest`, `deep digest` **and** user confirms heavy tier

## Do NOT

- Auto-trigger from `digest`, `full-digest`, or paper mentions
- Trigger on bare `digest` — ask tier first
- Run without `--confirm-heavy` on CLI
- Skip neighbor / theme / q- stub planning

## CLI

```bash
python3 -m meta.ingest deep-digest <raw> --confirm-heavy
python3 -m meta.ingest deep-digest <hub-slug> --row N --confirm-heavy   # course/series row
```

Same pipeline as `full-digest` plus extended `plan.json` (neighbor papers, q- stubs, `theme-*` threads).
Books are digested one part at a time (`--part N` / `--pages A-B`) — see full-digest § Books.
Course/series rows use `--row N`; the page type follows the raw format — see full-digest § Course / series rows.

## Output

`digestion-status: deep`, `status: digested`, Key equations + extended Connections required.

## Commit

The CLI commits this operation itself as `kb(digest): … (kb-x.y.z)` on main — only the files it changed (`--no-commit` to skip). Check with `pixi run ops -- log -n 1`. `finalize` is the commit point.
