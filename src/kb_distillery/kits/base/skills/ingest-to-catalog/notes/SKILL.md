---
name: ingest-to-catalog-notes
description: Catalog handwritten notes (ink-only PDFs) from inbox to raw/handwritten/. Corpus row only. Do NOT digest from here.
---

# ingest-to-catalog / notes

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on an inbox PDF with no text layer (reMarkable notebook, scan)

## Do NOT

- Digest from here — a digested handwritten file becomes a `lecture-` page (or, ≥60 pages, a
  `notebook-` collection with `part-` pages)
- Route typed notes here — typed notes belong in `printed-docs/`

## Behavior

1. Move to `raw/handwritten/<short>-<topic>.pdf` (`short` = the collection's `short:`)
2. Corpus row; with a course/series collection, a `—` Contents row is appended (`--title`)

## CLI

```bash
distill ingest catalog raw/inbox/<file>.pdf --collection course-runi-rl --title "Lecture 2 notes"
distill ingest catalog raw/inbox/<file>.pdf --format handwritten   # force
```
