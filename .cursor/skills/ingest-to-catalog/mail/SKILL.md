---
name: ingest-to-catalog-mail
description: Catalog a raw/inbox/mail-.../ thread bundle to raw/mail/ and create a type source wiki stub. Zero LLM. Do NOT digest from here.
---

# ingest-to-catalog / mail

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on an inbox `mail-*/` directory (from `scrap-data-mail`)

## Do NOT

- Digest — use easy/full/deep digest skills after catalog
- Hand-edit `raw/mail/` — it is immutable once cataloged, same as any `raw/` content

## Behavior

1. Move `raw/inbox/mail-<dir>/` → `raw/mail/<dir>/` (folder stays intact: `thread.md` +
   flat attachments)
2. Create `wiki/source-mail-<slug>.md` (slug = folder name minus the date prefix):
   `type: source`, `format: email`, `status: to-read`, `raw:` pointing at the
   **directory** (trailing slash) — same pattern as `format: course` pages
3. Run lint (via caller)

## CLI

```bash
python3 -m meta.ingest catalog raw/inbox/mail-<dir>
```

No `--course` — mail threads are flat under `raw/mail/`, not grouped by course.
