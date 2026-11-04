---
name: ingest-to-catalog-web
description: Catalog web clips from inbox to raw/web-clips/. Corpus row only. Do NOT digest from here.
audience: app
mode: write
---

# ingest-to-catalog / web

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on an inbox `.md`/`.html`/`.htm` that is not a chat export

## Do NOT

- Digest from here — a digested clip becomes an `article-` page

## Behavior

1. Move to `raw/web-clips/<topic>.<ext>` (prefixed with the collection's `short:` when it joins one)
2. Corpus row; with a course/series collection, a `—` Contents row is appended

## CLI

```bash
distill ingest catalog raw/inbox/<clip>.md [--collection <collection>]
```
