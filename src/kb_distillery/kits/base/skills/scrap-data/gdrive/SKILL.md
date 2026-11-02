---
name: scrap-data-gdrive
description: Pull files from a mounted Google Drive folder into raw/inbox/ with zero LLM tokens. Use for pull from drive, google drive, notes to obsedian, sync drive folder. Do NOT fetch Drive bytes through Google Drive MCP tools and do NOT hand-write cp loops.
---

# scrap-data / gdrive

**LLM tier:** none · **Budget:** 0 tokens

Default source is the My Drive folder **`Notes to Obsedian`** (misspelled on purpose — that is
its real name; it has also been spelled `notes-to-obsedian`). Folder matching is slug-based, so
either spelling resolves.

## Triggers

- `pull from drive`, `google drive`, `sync drive folder`
- `notes to obsedian`, `get the pdfs from drive`

## Do NOT

- **Never fetch Drive bytes through the Google Drive MCP tools.** `download_file_content`
  returns base64 into the agent context — the default folder holds a 284 MB PDF, which is
  unrecoverable that way. The local mount streams instead; that is what this skill uses.
- **Never hand-write `cp` loops or a size-verification loop.** The CLI already skips what the
  vault has, streams in chunks, and verifies every byte count.
- Do not debug a stalled mount by hand — see Mount stalls below.
- Do not catalog or digest from here — `ingest-to-catalog` and the digest skills do that.
- Do not write to `raw/` with agent tools; guard blocks it. Run the CLI.

## CLI

```bash
distill ingest scrap-gdrive --dry-run
distill ingest scrap-gdrive
distill ingest scrap-gdrive
```

Options: `--folder <name>` (default `Notes to Obsedian`), `--ext pdf,jpg,md` (default `pdf`),
`--warn-mb <n>` (default 100), `--account <email>` when several Drive accounts are mounted,
`--force` to bypass dedup.

## Agent steps

1. Run with `--dry-run` first. It is free — it reads sizes from mount metadata and downloads
   nothing.
2. Show the user the plan: what would be pulled, what is skipped, the total size, and any
   `WARNING` lines verbatim.
3. Get a yes, then re-run without `--dry-run`.
4. Run `distill lint` so new inbox files land in `meta/corpus.tsv` as `queued`.

## Behavior

1. Finds the mount under `~/Library/CloudStorage/GoogleDrive-*`; several accounts require
   `--account`.
2. Wakes a stalled mount (see below), then resolves the folder by slug.
3. Lists matching files, reading **size from metadata only** — no bytes move yet.
4. Skips any file whose `(name, size)` already exists anywhere under `raw/`. This is what makes
   a repeat pull cost roughly nothing.
5. Copies the rest with a chunked stream, then asserts the destination size matches the source;
   a partial file is deleted rather than left behind.
6. Re-checks each copied file by streaming sha1 against `meta/corpus.tsv`, catching duplicates
   that were renamed. A hit is deleted and reported as blocked.
7. Prints copied / skipped / blocked / failed counts.

**Filenames are preserved, not sanitized.** The inbox is a queue and `catalog` does the real
renaming; rewriting names here would orphan files already pulled and force a re-download.
Hebrew filenames survive intact.

## Size pushback

Files over `--warn-mb` (default 100) print a loud `WARNING` naming the file and its size. This
is **pushback, not a gate** — the pull always proceeds. Verification is the human answering
step 2 above, not the script refusing.

## Mount stalls

A mount whose File Provider extension is running without Google Drive.app fails as:

```
ls: fts_read: Operation timed out
```

The CLI detects this (a listing that does not return in 10 s), launches Google Drive.app, and
polls for up to 60 s. If it still fails, the account needs a manual sign-in.

## Next step

`ingest-to-catalog` to route the inbox into `raw/<format>/` folders (with `--collection` for course material).
