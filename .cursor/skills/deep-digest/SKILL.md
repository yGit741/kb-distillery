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
- Run without `--confirm-heavy` on CLI
- Skip neighbor / MOC / q- stub planning

## CLI

```bash
python3 -m meta.ingest deep-digest <raw> --confirm-heavy
```

Same pipeline as `full-digest` plus extended `plan.json` (neighbor papers, q- stubs, MOC threads).

## Output

`digestion-status: deep`, `status: digested`, Key equations + extended Connections required.
