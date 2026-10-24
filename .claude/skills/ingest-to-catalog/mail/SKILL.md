---
name: ingest-to-catalog-mail
description: Catalog a raw/inbox/mail-.../ thread bundle to raw/emails/ as a corpus row (no wiki stub). Zero LLM. Do NOT digest from here.
---

# ingest-to-catalog / mail

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on an inbox `mail-*/` directory (from `scrap-data-mail`)

## Do NOT

- Digest — use easy/full/deep digest skills after catalog (a digested thread is a `conversation-` page)
- Hand-edit `raw/emails/` — immutable once cataloged; only the agent `parsed.md` sidecar may be added
- Create a wiki stub — the thread stays a corpus row until it is worth digesting

## Behavior

1. Move `raw/inbox/mail-<YYYY-MM-DD-thread>/` → `raw/emails/<YYYY-MM-DD-thread>/` (folder stays
   intact: `thread.md` + flat attachments). `emails/` is the only nested raw folder.
2. Optional `--collection` → corpus `collection` on `thread.md` (+ a Contents row on a
   course/series collection)
3. Lint runs at the end

## CLI

```bash
python3 -m kb.ingest catalog raw/inbox/mail-<dir> [--collection <collection|person>]
```
