---
name: explore-raw-data
description: Look at cataloged raw sources (zero-LLM CLI) — find files, read excerpts, check a source against wiki pages, recommend a digest tier. Use for explore-raw-data, explore raw, which sources do I have on …, what does this undigested paper say, is this paper worth digesting, check this source against my notes. Do NOT answer thesis questions from the wiki, read raw/inbox/, digest, or write anything.
---

# explore-raw-data

**LLM tier:** light · **Budget:** ~2–6k tokens

The one door from the wiki to `raw/`. The CLI prints text and metadata; you reason over it. Read-only.

## Triggers

- `explore-raw-data`, `explore raw`
- `which sources do I have on …`, `what does this undigested paper say`
- `is this paper worth digesting`, `check this source against my notes`

## Do NOT

- Answer thesis questions from the wiki (that is `query-knowledge`)
- Read `raw/inbox/` — catalog first (`ingest-to-catalog`); the CLI refuses with exit 2
- Digest (that is the digest ladder) or write anything (strictly read-only)
- Open PDFs with Read — use `read` so extraction and page limits apply

## CLI

```bash
python3 -m meta.explore_raw find "<question>" --limit 10 [--all]
python3 -m meta.explore_raw read <raw-path> [--pages A-B] [--max-pages N]
python3 -m meta.explore_raw check <raw-path> --pages-of <slug> [<slug>…] [--pages A-B]
python3 -m meta.explore_raw recommend <raw-path>
```

## Agent steps

1. **Find** — `find` ranks corpus rows by filename, collection, cited page and (for text clips) the first lines. PDFs are matched by name and metadata only.
2. **Pick rows** — 1–3 files. Rows marked `UNDIGESTED` are queued: no wiki page reflects them yet; say so explicitly.
3. **Read / check** — `read` for excerpts; `check <raw> --pages-of <slug>` prints the source beside the page's claims and takeaways, and you compare. Cite the raw path and why you opened it for every sentence drawn from it.
4. **Recommend** — `recommend <raw>`, then end with skip / easy / full / deep and a one-line reason. When pages already exist, add: run `query-knowledge` for what the wiki already says.

## Output

Chat only. Nothing is written.

## Quality bar

Every raw-derived claim carries its raw path; undigested files are labelled; the answer ends with a tier recommendation.

## Next step

`easy-digest` / `full-digest` / `deep-digest` (ask the user, never auto-run), or `ingest-to-catalog` if the file is still in the inbox.
