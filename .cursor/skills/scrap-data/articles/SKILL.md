---
name: scrap-data-articles
description: Download arXiv or PDF URLs to raw/inbox/. Use with scrap-data when the source is a paper or preprint URL.
---

# scrap-data / articles

**LLM tier:** none · **Budget:** 0 tokens

## CLI

```bash
python3 -m meta.ingest scrap <arxiv-or-pdf-url> --type articles
```

## Behavior

- arXiv `abs/` URLs → PDF download to `raw/inbox/<year>-<slug>.pdf` (best-effort naming)
- Direct `.pdf` URLs → saved with sanitized filename
- Local `.pdf` path → copied to inbox

## Do NOT

- Rename to final `raw/papers/` path — `ingest-to-catalog/articles` does that
- Read PDF content
