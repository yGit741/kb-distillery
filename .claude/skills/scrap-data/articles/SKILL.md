---
name: scrap-data-articles
description: Download arXiv or PDF URLs to raw/inbox/. Use with scrap-data for paper URLs. Do NOT catalog or digest from here.
---

# scrap-data / articles

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- Paper or arXiv URL with `scrap-data --type articles`

## CLI

```bash
python3 -m meta.ingest scrap <arxiv-or-pdf-url> --type articles
```

## Behavior

- arXiv `abs/` URLs → PDF download to `raw/inbox/<year>-<slug>.pdf` (best-effort naming)
- Direct `.pdf` URLs → saved with sanitized filename
- Local `.pdf` path → copied to inbox

## Do NOT

- Rename to final `raw/printed-docs/` path — `ingest-to-catalog/articles` does that
- Read PDF content
