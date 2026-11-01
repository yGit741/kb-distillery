---
name: ingest-to-catalog-slides
description: Catalog slide decks from inbox to raw/presentations/. Corpus row only. Do NOT digest from here.
---

# ingest-to-catalog / slides

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on an inbox `.ppt`/`.pptx`/`.key`, or a slide-deck PDF with `--format presentations`

## Do NOT

- Digest from here — a digested deck becomes a `lecture-` page via `full-digest <collection> --row N`

## Behavior

1. Move to `raw/presentations/<short>-<topic>.<ext>` (`short` = the collection's `short:`)
2. Corpus row; with a course/series collection, a `—` Contents row is appended (`--title`)

## CLI

```bash
python3 -m kb_distillery.ingest catalog raw/inbox/<deck>.pdf --format presentations --collection course-runi-rl --title "Lecture 3 · DP"
```
