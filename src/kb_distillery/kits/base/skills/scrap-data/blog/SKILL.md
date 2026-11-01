---
name: scrap-data-blog
description: Pull every post of a WordPress.com blog into raw/inbox/ as Markdown clips with lossless math and downloaded figures (0 LLM). Use for scrap blog, pull the blog, archive a wordpress blog. Do NOT catalog or digest from here.
---

# scrap-data / blog

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `scrap blog <site>`, `pull the whole blog`, `archive <name>'s blog`
- A single post URL on a WordPress.com site → the same command with `--since <its date> --limit 1`

## Do NOT

- Pull without the collection: the clip prefix is the series collection's `short:` (create the `series-` page first, `wiki-edit`)
- Catalog or digest from here — `drain-inbox --collection <series-slug>` is the next step
- Pull a self-hosted WordPress (its API is `/wp-json/wp/v2/`, not supported yet) — scrap posts one by one

## CLI

```bash
distill ingest scrap-wordpress gilkalai.wordpress.com --prefix kalai-blog           # whole blog
distill ingest scrap-wordpress gilkalai.wordpress.com --prefix kalai-blog --limit 5 # trial run
distill ingest scrap-wordpress gilkalai.wordpress.com --prefix kalai-blog --since 2026-01-01
distill ingest scrap-wordpress <site> --prefix <short> --no-images                   # figures stay remote
```

## Behavior

1. Posts come from the public REST API (`public-api.wordpress.com/rest/v1.1/sites/<site>/posts`), oldest first,
   100 per page; posts whose URL is already a clip in `raw/web-clips/` or the inbox are skipped (`--force` re-pulls).
2. One clip per post: `raw/inbox/<prefix>-<YYYY-MM-DD>-<slug>.md` with frontmatter (title, url, date, categories,
   counts, `tags: [source/wordpress, blog/<site>]`) — no `type:`, so it stays a raw file.
3. Math: WordPress.com's `latex.php` images carry the TeX source in the URL → `$…$`, `\displaystyle` → `$$…$$`. Lossless.
4. Figures: downloaded (8 in parallel) to `raw/inbox/<clip stem>-NN.<ext>`, linked as `../images/<file>` with the
   original URL as the link title; a figure that cannot be fetched keeps its remote URL. `<iframe>` → a link line.
5. HTML → Markdown is `src/kb_distillery/ingest/htmlmd.py` (standard library only).

## Next step

`distill ingest drain-inbox --collection <series-slug> --match <prefix>-` — clips first, then their figures; one lint and one
`kb(catalog)` commit for the whole drain. Figures land in `raw/images/` as `asset:<clip>` rows.

## Commit

`scrap-wordpress` commits itself as `kb(import): <n> WordPress clips and figures into the inbox (kb-x.y.z)`
(`--no-commit` to skip). Figures are gitignored binaries tracked by `meta/corpus.tsv`, like PDFs.
