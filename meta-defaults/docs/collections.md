# Collections: courses, series, books

> Contents tables, partitions and how their rows are digested. Part of the doc router in [`AGENTS.md`](../../AGENTS.md).

## Course and series collections

A `course-` / `series-` page is a collection over member raw files: Overview → Contents → Threads
(`src/kb_distillery/core/hubs.py`, `meta/templates/course.md`, `series.md`). Each Contents row is one source —
usually one file, sometimes several (slides + the handwritten notes taken in that lecture):

```
| # | Item | Raw | Status | Note |
|---|------|-----|--------|------|
| 1 | Lecture 1 · Introduction | `raw/presentations/rl-lecture-01-introduction.pdf` | full | [[lecture-rl-01-introduction]] |
| 2 | Lecture 2 · MDPs | `raw/presentations/rl-02.pdf` `raw/handwritten/rl-mdp.pdf` | — | |
| 3 | Course book | `raw/printed-docs/rl-course-book.pdf` | partial | [[book-rl-course-book]] |
```

Row status: `skip` | `—` (backlog) | `partial` (the row is itself a book/notebook collection) | `easy` |
`full` | `deep` (the source's depth). **The table is the truth for member dispositions** — a `—` row is backlog.
A row's identity is its raw paths; `#` is display order. The collection's `status` follows its rows.

## Digesting a collection row

**Digesting a collection row:** `full-digest|deep-digest <collection-slug> --row N`. The page type follows the
format: `presentations/`, `handwritten/` → `lecture-`; `emails/` → `mail-`; `web-clips/`
or non-PDF `printed-docs/` → `article-`; `printed-docs/` PDF → `paper-`. LLM chats become `chat-`
pages through the chat pipeline instead. `finalize` ticks the row; `easy-digest` ticks it too and
sets `status: digested`. A raw path that is a collection member auto-scopes to its row.

## Books and parts

**Books are a collection plus parts.** A PDF of ≥60 pages is a book. It gets one `type: book` page
(slug `book-<PDF stem>`; a long handwritten PDF is a `notebook-<stem>`) holding an `## Overview` paragraph and a `## Partition` table that splits
pages `1..book_pages` into **disjoint, exhaustive parts** — a part can be a chapter, merged short
chapters or half a long one; front/back matter rows are `skip`. Each digested part is its own
`type: part` page (slug `part-<book stem>-<topic>`); undigested parts are table rows, not pages.

```
| # | Part | Pages | Status | Note |
|---|------|-------|--------|------|
| 1 | Front matter · Prefaces | 1–18 | skip | |
| 2 | Chapter 1. Boolean functions and the Fourier expansion | 19–42 | full | [[part-2014-analysis-of-boolean-functions-ch1-fourier-expansion]] |
| 3 | Chapter 2. Basic concepts and social choice | 43–68 | — | |
```

Digesting a book is always scoped — the CLI prints the partition and exits 2 instead of guessing:

```
python3 -m kb_distillery.ingest toc <raw>                     # partition [x]/[ ]/[-]; --depth 2 adds the outline
python3 -m kb_distillery.ingest full-digest <raw> --part 3    # a row of the partition
python3 -m kb_distillery.ingest full-digest <raw> --pages 43-55  # carves a new part out of undigested rows
python3 -m kb_distillery.ingest full-digest <raw> --section 2 # an outline entry (chapter number, #index, text)
python3 -m kb_distillery.ingest full-digest <raw> --whole-book  # override the gate (writes a paper)
```

The first scoped digest creates the book page from `meta/templates/book.md` with a partition
proposed from the PDF outline (split only at chapter/section boundaries, ≤60 pp per part); write
its Overview by hand. `finalize` writes the `type: part` page and ticks its row. A part's identity
is its page range — the `#` column is display order and renumbers when a row is split.

**The partition is the truth** (`src/kb_distillery/core/books.py`, checked by lint): gaps or overlaps are errors,
a part over 60 pages is a warning, a digested row must link its part page and match its
`depth`, and the part's `book:`/`raw:`/`section_pages:` must agree with its row.
Coverage = digested pages ÷ non-skip pages; below 100% the raw file is `partial` in
`meta/corpus.tsv` — never `source` — warns on every run and counts in `--health` as
`partial-books`. The book's `status` follows coverage. Re-digesting a finished part is refused.
