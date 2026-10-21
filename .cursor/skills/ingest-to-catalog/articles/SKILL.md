---
name: ingest-to-catalog-articles
description: Catalog a typed PDF from inbox to raw/printed-docs/ and create a paper- wiki stub (or a course row). Zero LLM. Do NOT digest from here.
---

# ingest-to-catalog / articles

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on an inbox PDF with a text layer (typed, even if annotated)

## Do NOT

- Digest — use easy/full/deep digest skills after catalog

## Behavior

1. **Paper** (no collection, or a `book-`/person collection):
   1. Validate or suggest `YYYY-kebab-title.pdf` (arXiv scrapes are looked up for title/year/authors)
   2. Move to `raw/printed-docs/<year>-<title>.pdf`
   3. Create `wiki/paper-<year>-<title>.md` stub: `digestion-status: catalog`, `status: to-read`
   4. Person collection (researcher bibliography) → corpus `collection` = person slug
2. **Course/series member** (`--collection course-…|series-…`, e.g. a course book or typed notes):
   move to `raw/printed-docs/<short>-<topic>.pdf`, append a `—` Contents row, no wiki stub
3. Lint runs at the end

## CLI

```bash
python3 -m meta.ingest catalog raw/inbox/<file>.pdf
python3 -m meta.ingest catalog raw/inbox/<file>.pdf --collection nadav-cohen
python3 -m meta.ingest catalog raw/inbox/<file>.pdf --collection course-runi-rl --title "Course book"
```

A PDF of ≥60 pages is a book: digest it scoped (`toc`, `--part`), which creates its `book-` hub.
