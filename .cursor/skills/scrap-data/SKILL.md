---
name: scrap-data
description: Save URLs or files to raw/inbox/ with zero LLM tokens. Use for "scrap", "download", "save to inbox", or fetching a paper URL. Do NOT use for cataloging or digesting.
---

# scrap-data

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `scrap`, `download`, `save to inbox`, `fetch this URL`
- `scrap article`, `download paper`

## Do NOT

- Write to `raw/` via agent tools — run the CLI (guard blocks direct writes)
- **Scrap without `resolve` first** — always run `python3 -m meta.ingest resolve <query>`; if FOUND, cite `[[slug]]` instead
- Catalog or digest — use `ingest-to-catalog` or digest skills next
- Trigger any digest tier from here

## CLI

```bash
python3 -m meta.ingest resolve <url|arxiv|slug|title>   # check vault first (0 LLM)
python3 -m meta.ingest scrap <url|path> [--type articles|notes|slides|web|blog]
python3 -m meta.ingest scrap <url> --force              # override dedup block
```

Scrap is **blocked** when resolve finds a match or bytes already exist in `raw/`. Use `--force` only when intentional.

## Subskills (route by `--type` or auto-detect)

| Subskill | Path | Status |
|----------|------|--------|
| [articles](articles/SKILL.md) | arXiv/PDF URL → inbox | implemented |
| [notes](notes/SKILL.md) | reMarkable / handwritten | stub |
| [slides](slides/SKILL.md) | lecture decks | stub |
| [web](web/SKILL.md) | HTML/markdown clip | stub |
| [blog](blog/SKILL.md) | blog posts | stub |

## Next step

After scrap: `python3 -m meta.ingest catalog raw/inbox/<file>` or `drain-inbox`.
