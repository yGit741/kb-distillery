---
name: ingest-to-catalog-blog
description: Catalog blog posts from inbox to raw/web-clips/ (or raw/printed-docs/ with --format). Corpus row only. Do NOT digest from here.
---

# ingest-to-catalog / blog

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog` on an inbox blog post (`.md`, `.html`)

## Do NOT

- Digest from here — a digested post becomes an `article-` page

## Behavior

1. `.md`/`.html` is detected as `web-clips`; pass `--format printed-docs` for a typed post saved
   as part of a course's printed material
2. Flat name `<short>-<topic>.<ext>` when it joins a course/series (e.g. `blog-not-exact-<post>.md`)
3. Corpus row only; with a course/series collection, a `—` Contents row is appended
4. `scrap-wordpress` clips (`tags: [source/wordpress, …]`, no registered blog tag) go to `raw/web-clips/`;
   their `<stem>-NN.<ext>` figures follow to `raw/images/` as `asset:<clip>` companions

## CLI

```bash
python3 -m meta.ingest catalog raw/inbox/<post>.md --collection <hub> [--format printed-docs]
```
