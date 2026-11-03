---
name: scrap-data
description: Save URLs or files to raw/inbox/ with zero LLM tokens. Use for "scrap", "download", "save to inbox", or fetching a paper URL. Do NOT use for cataloging or digesting.
audience: app
mode: write
---

# scrap-data

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `scrap`, `download`, `save to inbox`, `fetch this URL`
- `scrap article`, `download paper`
- `pull from drive`, `google drive`, `notes to obsedian` → `gdrive` subskill
- a YouTube link, `save this lecture/video` → `youtube` subskill

## Do NOT

- Write to `raw/` via agent tools — run the CLI (guard blocks direct writes)
- **Scrap without `resolve` first** — always run `distill ingest resolve <query>`; if FOUND, cite `[Title](slug.md)` instead
- Catalog or digest — use `ingest-to-catalog` or digest skills next
- Trigger any digest tier from here

## CLI

```bash
distill ingest resolve <url|arxiv|slug|title>   # check vault first (0 LLM)
distill ingest scrap <url|path> [--type articles|notes|slides|web|blog]
distill ingest scrap <url> --force              # override dedup block
distill ingest scrap-mail <mbox-or-eml> [--slug thread-slug] [--force]
distill ingest scrap-gdrive --dry-run           # preview a Drive folder pull (0 bytes)
distill ingest scrap-wordpress <site> --prefix <collection short> [--since YYYY-MM-DD] [--limit N] [--no-images] [--force]
distill ingest scrap-youtube <url> [--force]   # transcript + anchors with thumbnails, 0 LLM
```

Scrap is **blocked** when resolve finds a match or bytes already exist in `raw/`. Use `--force` only when intentional.

## Subskills (route by `--type` or auto-detect)

| Subskill | Path | Status |
|----------|------|--------|
| [articles](articles/SKILL.md) | arXiv/PDF URL → inbox | implemented |
| [mail](mail/SKILL.md) | local `.mbox`/`.eml` export → thread bundle | implemented |
| [gdrive](gdrive/SKILL.md) | mounted Google Drive folder → inbox | implemented |
| [notes](notes/SKILL.md) | reMarkable / handwritten | stub |
| [slides](slides/SKILL.md) | lecture decks | stub |
| [web](web/SKILL.md) | HTML/markdown clip | stub |
| [blog](blog/SKILL.md) | a whole WordPress.com blog → clips + figures | implemented (`scrap-wordpress`) |
| [youtube](youtube/SKILL.md) | a YouTube lecture/video → `video-<name>/` bundle: transcript by chapter + scored anchors with thumbnails | implemented (`scrap-youtube`) |

## Next step

After scrap: `distill ingest catalog raw/inbox/<file>` or `distill ingest drain-inbox`.

## Commit

Scraping a PDF commits nothing: the binary is gitignored and lands in `raw/inbox/`; its `meta/corpus.tsv` row (and the `kb(catalog)` commit) appears when you catalog it. Text clips and other tracked files are committed as `kb(import): … (kb-x.y.z)` (`--no-commit` to skip) — check with `distill ops log -n 1`. A non-arXiv `.pdf` URL is saved on the `articles` path and its source URL is remembered in `meta/.catalog/sources.jsonl`, so catalog fills the stub's `url:`.
