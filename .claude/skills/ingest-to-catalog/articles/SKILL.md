---
name: ingest-to-catalog-articles
description: Catalog a PDF from inbox to raw/papers/ and create a wiki stub. Zero LLM. Do NOT digest from here.
---

# ingest-to-catalog / articles

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on inbox PDF

## Do NOT

- Digest — use easy/full/deep digest skills after catalog

## Behavior

1. Validate or suggest `YYYY-kebab-title.pdf` naming
2. Move to `raw/papers/<course>/`
3. Create `wiki/<slug>.md` stub: `digestion-status: catalog`, `status: to-read`
4. Run lint (via caller)

## CLI

```bash
python3 -m meta.ingest catalog raw/inbox/<file>.pdf [--course misc]
```

Default course folder: `misc` (override with `--course`).
