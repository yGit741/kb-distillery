---
name: full-digest
description: Deepen a Source page to depth full via transactional ingest (~8-12k tokens, medium tier). Use ONLY for "full-digest" or "full digest". Do NOT use for bare "digest", "easy-digest", or "deep-digest".
---

# full-digest

**LLM tier:** medium · **Budget:** ~8–12k tokens in

Replaces legacy `thesis-ingest`.

## Triggers

- `full-digest`, `full digest`, `read this paper fully`

## Do NOT

- Trigger on bare `digest` — ask tier first
- Trigger on `easy-digest` or `deep-digest`
- Write `wiki/` directly during an open session
- Mark as heavy tier

## Commands

```bash
python3 -m kb.ingest full-digest <raw>   # opens session, prints next steps
python3 -m kb.ingest begin <raw>         # same session API
python3 -m kb.ingest extract <sha>       # fill claims.json — see backend/src/kb/ingest/extract_prompt.md
python3 -m kb.ingest map <sha>
python3 -m kb.ingest draft <sha>
python3 -m kb.ingest finalize <sha>      # lint --ingest-strict for depth full
python3 -m kb.ingest abort <sha>
```

## Agent steps after `begin` / `full-digest`

1. Run `extract` — read `meta/.ingest/<sha>/extracted.text` (first 25 pages). If
   the raw entity has a `parsed.md` sidecar (e.g. `raw/emails/<YYYY-MM-DD-thread>/parsed.md`),
   `extracted.text` is that sidecar's content instead of raw PDF/thread text.
2. Write `claims.json` with real LaTeX equations, results, ideas.
3. Set `person` when the raw file's corpus `collection` names a person page (researcher bibliography).
4. Re-run `extract` to validate.
5. `map` → `draft` → review `staging/` → `finalize`. Each new `q-` stub in `staging/` needs a short H1 (≤ 80 chars, the question's name) and its formal statement under `## Question` — fill it before `finalize`.

## Books (≥60 pages)

A book is digested one **part** at a time — never whole. `toc` prints the book's partition
(or a proposed one if the book has no `type: book` page yet):

```bash
python3 -m kb.ingest toc <raw>                     # [x] digested · [ ] backlog · [-] skip
python3 -m kb.ingest full-digest <raw> --part N    # a row; --pages A-B carves a new one
```

The session id is `<sha>-p<A>-<B>`. `map` names the page `part-<book stem>-<topic>` with
`type: part`; `finalize` ticks the row on the `book-<stem>` page (creating it on the first part;
a long handwritten PDF gets a `notebook-<stem>` collection instead).
`claims.json` `title` is the part's title; set `book_title` too when the book page is new.
After the first part, write the book page's `## Overview` paragraph — lint warns until it exists.

## Course / series rows

A `course-`/`series-` collection's `## Contents` table lists its member raw files. Digest one row by
passing the collection slug (the row's raw files are read together, e.g. slides + handwritten notes):

```bash
python3 -m kb.ingest full-digest course-runi-rl --row 3
```

The page type follows the raw format: `presentations/`, `handwritten/` → `lecture-`;
`emails/` → `conversation-`; `web-clips/` or non-PDF `printed-docs/` → `article-` (a tagged blog
post → `blog-`); `printed-docs/` PDF → `paper-`. LLM chats (`llm-chats/`) are not digested here —
they become `chat-` pages through the chat pipeline, which needs their `meta/chats/` tree.
`finalize` ticks the row (`full`) and links the new page. Passing a raw path that is a collection
member auto-scopes to its row.

## Output

A Source page (`layer: source`) at `depth: full`, `status: digested`, Key equations required at finalize.
An existing page (e.g. `depth: listed` or `easy`) is deepened in place. For a book: a `type: part`
page plus an updated partition row. For a collection row: a Source page plus a ticked Contents row.

## Quality bar

- Key equations: real LaTeX, not `—`
- Ideas link to existing wiki slugs
- topic pages (`theme-*`) `## Papers` updated via finalize
- Person link when the raw file's `collection` names a researcher

## Pitfalls

- The negation-word polarity check is now a warning (score capped at 60): it only fires when a negation sits within a few tokens of topic words the other page asserts, and never between a paper and its own new stubs. Do not reword honest assumptions to silence it; `coherence dismiss <id>` if it is spurious.
- A paper with long appendices (60+ pages) is treated as a paper when it has an abstract and no chapter outline; otherwise pass `--whole-book`.
- Idea and `q-` stubs are registered with the session automatically (map and finalize), so an aborted finalize removes them and restores topic-page `## Papers` lines; the old `staging/` is kept as `staging-aborted-<time>/`, and `begin` restores `claims.json`/`plan.json` of an aborted session.
- Topic slugs in `claims.json` `concepts` (a protocol key, kept) map to `area:`, not to new idea pages.

## Commit

The CLI commits this operation itself as `kb(digest): … (kb-x.y.z)` on main — only the files it changed (`--no-commit` to skip). Check with `pixi run ops -- log -n 1`. `finalize` is the commit point.
