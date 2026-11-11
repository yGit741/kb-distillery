# Raw layout, corpus manifest, naming

> Where raw files live, how `meta/corpus.tsv` tracks them, how they are named. Part of the doc router in [`AGENTS.md`](../../../../../../AGENTS.md).

## Raw layout

```
raw/inbox/              the single unclassified queue. Any shape. Drains (warn >30 days, error ≥50 files)
raw/printed-docs/       typed: papers, books, course books, typed notes, blog posts
raw/handwritten/        by hand: reMarkable notebooks, handwritten summaries
raw/presentations/      slide decks (pdf, pptx, key)
raw/llm-chats/          LLM conversation exports (md)
raw/emails/<YYYY-MM-DD-thread>/  thread.md + attachments + parsed.md sidecar — the only nested folder
raw/web-clips/          Web Clipper pages (md, html)
raw/images/             screenshots, figures
raw/videos/<name>/      video.md + video.json + transcript.vtt + info.json + a-<s>.jpg anchor thumbnails (scrap-youtube) — nests like emails/
wiki/                   flat agent-owned notes; filename prefix = type
think/                  human slow space (not linted)
_quarantine/            staged for deletion, gitignored, not part of the vault
```

`raw/` is split by **format** (how the bytes were produced), never by course or person, and is flat
below the format folder (except `emails/` and `videos/`, one folder per thread / video). Split rule: typed → `printed-docs/` (even if annotated), by hand →
`handwritten/` (catalog detects this from the PDF text layer), slides → `presentations/` whatever
the extension. Membership lives in the corpus `collection` column — **a raw file never moves after
catalog**; reclassifying it means editing that cell.

## The corpus manifest

`meta/corpus.tsv` has one row per file in `raw/`. Nothing can be silently forgotten.
Columns: `path sha1 kind disposition slug collection` — hand-edit only `disposition` and `collection`.

| disposition | meaning |
|-------------|---------|
| `queued` | keep, not yet written up — **the real backlog** |
| `source` | a Source page (or book/notebook) cites it via `raw:` |
| `partial` | **a book with only some parts digested** — the rest is still backlog |
| `skip` | explicitly not worth a note (a decision, not neglect) |
| `sidecar` | agent-written `parsed.md` inside an email thread folder |
| `dupe:<path>` | superseded by another file |
| `ink:<path>` | reMarkable annotation overlay belonging to `<path>` |
| `asset:<path>` | a figure downloaded with the web clip `<path>` (`raw/images/<clip stem>-NN.<ext>`), or any file of a video bundle besides its `video.md` (frames, transcript, data) — part of that item, never backlog or a collection member of its own |

The linter maintains it: a new file appears as `queued`; a file gone from disk is removed; **a sha1 change on a `source` file re-opens it as `queued`** — so re-annotating a paper on the tablet automatically re-queues it.

**`collection`** — comma-separated collection or person slugs the file belongs to (`course-runi-rl`,
`book-…`, `series-…`, or a researcher's person page such as `nadav-cohen` for their
bibliography). Lint checks every slug is a collection or person page, and that each course/series
`## Contents` table lists **exactly** the files whose `collection` names it.

Course and series Contents tables: see [`collections.md`](collections.md).

## Naming

Every format folder except `emails/` is flat; names are lowercase ASCII kebab, unique across the
vault. Papers and books use **`<year>-<kebab-title>.pdf`** — sortable, greppable, and the year is
metadata you would otherwise have to open the file to find.

```
2023-toolformer.pdf
1948-a-mathematical-theory-of-communication.pdf
```

The linter enforces the pattern and cross-checks the filename year against the digest's `year:` frontmatter, so the two cannot drift apart.

Other members of a course/series are named **`<short>-<topic>.<ext>`**, where `short` is the collection's
`short:` frontmatter (`rl-lecture-01-introduction.pdf`). Email thread folders are
`<YYYY-MM-DD>-<kebab-thread>`. Older origin-named sources keep their prefixes:

| Origin | Pattern | Example |
|---|---|---|
| לא מדויק blog (gadial.net) | `blog-not-exact-<post>` | `blog-not-exact-jordan-form-in-practice.md` |
| Linear Algebra 1 | `linear-algebra-1-<daniel-notes-on-maman\|course-book\|theorem-and-definitions>-<topic>` | `linear-algebra-1-daniel-notes-on-maman-01.pdf` |
| Linear Algebra 2 | `linear-algebra-2-course-book-<part>` | `linear-algebra-2-course-book-part-a.pdf` |

Provenance is kept, not lost: the original name lives in `meta/raw-renames.tsv` (old → new; the one-off script that applied it, `rename_raw.py`, is retired) and, for `.md`, in frontmatter `original_name`/`title`/`aliases`. Raw `.md` files carry filter tags — `source/blog-not-exact`, `source/course-book`, `source/daniel-notes-on-maman`, `source/theorem-and-definitions`, `subject/<x>`, `course/<x>`; PDFs are filtered by filename prefix (`file:linear-algebra-1-`).

⚠️ reMarkable's `X (annotations).pdf` exports are **ink-only overlays**, not annotated documents — typically a few KB against a multi-MB source, and unreadable on their own. They have all been deleted. If new ones appear, do not delete the source document in their favour.

## Adding sources from the app

Two endpoints add sources with no model call (`src/kb_distillery/services/inbox_add.py`, router `inbox_add.py`):

- `POST /api/inbox/files` (multipart, field `files`, one or more): each file is saved under `raw/inbox/` through the kb's storage connector, then catalogued as `distill ingest` drains the inbox. A file is `refused` when `catalog` has no format for its extension (`.pdf`, slides, `.md`/`.html`, images), `duplicate` when its sha1 is already in `meta/corpus.tsv`, in the inbox or earlier in the same upload, else `added` with its `raw_path`. A name that is taken keeps both files (`-2` suffix). Body cap: 64 MB (`security.UPLOAD_PATHS`).
- `POST /api/inbox/link-folder` `{path}`: an absolute folder outside the kb (and not containing it). Its supported files (at most 500 files / 512 MB, hidden files and symlinks skipped) go through the same save-and-catalog path, so linking the same folder again finds every file as a duplicate and commits nothing. Nothing is written to `kb.toml`: `[storage]` names the connector for the kb's own `raw/`, and a folder of loose sources is not that.

Each call that adds something is one knowledge step, `kb(catalog): add N sources from the app` or `kb(catalog): link folder <name>` (`catalog` is the op for sources entering `raw/`). A read-only server (`KB_READ_ONLY=1`) answers 405; an open ops session answers 409.

## Ingest from the app

The Ingest screen (flag `ui.ingest`, `/ingest`; the form on top and under it an inbox of everything brought in, grouped as In progress (live), Waiting for your review (links to the proposal), Done and Did not finish; Try again re-sends a web address, a file has to be dropped again; the wizard layout keeps its own progress card and shows no list; `src/kb_distillery/services/ingest_ui.py`, router `ingest_ui.py`) takes a file (PDF, Markdown, text, HTML) or a pasted URL, a digest tier (`listed`, `easy`, `full`, `deep`) and an optional collection page, and ends in a proposal, never a page.

- `POST /api/ingest` (multipart `file` + `tier`, `collection`, `backend`; or JSON `{url, tier, collection, backend}`) answers `{job_id}` at once. A file type outside the list is 415; a URL must be public http(s) (no localhost, private addresses or credentials) or 422. `GET /api/ingest/{job_id}` is `{status, steps, pages, proposal_id?, error?}`; `GET /api/ingest/{job_id}/events` is the same over SSE (`job` on every change, `end` when it stops). `GET /api/ingest` lists the last 200 jobs newest first (`id`, `source`, `kind` file|url, `tier`, `collection`, `backend`, `started`, `finished`, `status` running|done|failed|interrupted, `step`, `error`, `proposal_id`, plus `proposal_status` open|stale|applied|rejected|undone and `proposal_updated`, both read from the proposals each time, never copied); it also answers on a read-only server. Each job's public record is kept as small JSON in `<kb>/.local/ingest/<id>.json` (kb-local, untracked, written atomically), so the list survives a restart; a record still `running` that no thread of this server owns is reported as `interrupted`. The proposal outlives the job.
- The job runs `fetch` (URLs), `convert` (the bytes are saved and catalogued through the inbox code, one `kb(catalog)` step, and their text is read), `digest` (one call through `kb_distillery.llm` on the request's `backend`; `listed` makes no call; `easy`/`full`/`deep` use the `light`/`standard`/`strong` model tiers and read 12k/60k/100k characters) and `propose` (ONE proposal, producer kind `ingest`, context `{source, tier, collection}`): a `create_page` op for the source page and each new idea (at most four), an `edit_page` op for an idea that already exists (one more bullet under `## Connections`, `## My notes` untouched) and for catalog's depth-listed stub of a paper.
- Catalog's own bookkeeping is unchanged and is the only thing that lands before review: the raw file, its `meta/corpus.tsv` row, a paper's listed stub, and, for a course or series `collection`, its Contents row.
