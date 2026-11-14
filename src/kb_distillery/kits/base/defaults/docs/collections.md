# Collections: courses, series, books

> Contents tables, book chapters and how their rows are digested. Part of the doc router in [`AGENTS.md`](../../../../../../AGENTS.md).

## Course and series collections

A `course-` / `series-` page is a collection over member raw files: Overview → Contents → Threads
(`src/kb_distillery/vault/hubs.py`, `meta/templates/course.md`, `series.md`). Each Contents row is one source —
usually one file, sometimes several (slides + the handwritten notes taken in that lecture):

```
| # | Item | Raw | Status | Note |
|---|------|-----|--------|------|
| 1 | Lecture 1 · Introduction | `raw/presentations/rl-lecture-01-introduction.pdf` | full | [Lecture 1 · Introduction](lecture-rl-01-introduction.md) |
| 2 | Lecture 2 · MDPs | `raw/presentations/rl-02.pdf` `raw/handwritten/rl-mdp.pdf` | — | |
| 3 | Course book | `raw/printed-docs/rl-course-book.pdf` | partial | [Course book](book-rl-course-book.md) |
```

Row status: `skip` | `—` (backlog) | `partial` (the row is itself a book/notebook collection) | `easy` |
`full` | `deep` (the source's depth). **The table is the truth for member dispositions** — a `—` row is backlog.
A row's identity is its raw paths; `#` is display order. The collection's `maturity` follows its rows.

## Digesting a collection row

**Digesting a collection row:** `full-digest|deep-digest <collection-slug> --row N`. The page type follows the
format: `presentations/`, `handwritten/` → `lecture-`; `emails/` → `mail-`; `web-clips/`
or non-PDF `printed-docs/` → `article-`; `printed-docs/` PDF → `paper-`. LLM chats become `chat-`
pages through the chat pipeline instead. `finalize` ticks the row; `easy-digest` ticks it too and
sets `maturity: digested`. A raw path that is a collection member auto-scopes to its row.

## Books and chapters

**Books are a collection of chapters.** A PDF of ≥60 pages is a book. Filing it (`catalog`) builds the
whole book first: one `type: book` page (slug `book-<PDF stem>`; a long handwritten PDF is a
`notebook-<stem>`, built with `ingest book <raw>`) holding an `## Overview` paragraph and a `## Chapters`
table that splits pages `1..book_pages` into **disjoint, exhaustive chapters**. The table comes from the
PDF outline, falling back to chapter headings at the top of pages; front and back matter rows are
`skip`, and exercises or end-of-chapter notes fold into their chapter. When neither gives numbered
chapters, ingest stops with an error and leaves the PDF where it is — it never guesses. Supply the
breaks by hand with `--chapters-file <file>`, one chapter per line, tab-separated:

```
front	Front matter · Preface	1-18
ch1	Chapter 1. Boolean functions and the Fourier expansion	19-42
ch2	Chapter 2. Basic concepts and social choice	43-68
back	Bibliography · Index	391-419
```

From then on the raw file is `partial` in `meta/corpus.tsv` until every chapter is digested.

```
| Id | Chapter | Pages | Status | Note |
|----|---------|-------|--------|------|
| front | Front matter · Prefaces | 1–18 | skip | |
| ch1 | Chapter 1. Boolean functions and the Fourier expansion | 19–42 | full | [Chapter 1](part-2014-analysis-of-boolean-functions-ch1-fourier-expansion.md) |
| ch2 | Chapter 2. Basic concepts and social choice | 43–68 | — | |
```

**Each row has a fixed id**, the book's own numbering: `ch1`, `ch11`, `appA`, plus `front` and `back`.
A row keeps its id forever. A very long chapter stays whole (lint only warns); split it by hand into
lettered rows `ch11a`, `ch11b`. Rows are never merged. The id is the part page's `chapter: ch3`, the
middle of its slug (`part-<book stem>-ch3-<topic>`) and the suffix of its citekey.

Digest works by chapter only, one `type: part` page per chapter; digesting a book before its book page
exists is refused with a hint to ingest it first:

```
python3 -m kb_distillery.ingest book <raw> [--chapters-file F]   # build the book page of an already filed PDF
python3 -m kb_distillery.ingest toc <raw>                     # chapters [x]/[ ]/[-] with ids; --depth 2 adds the outline
python3 -m kb_distillery.ingest full-digest <raw> --chapter 3     # one chapter (3, ch3, ch11a, appA)
python3 -m kb_distillery.ingest full-digest <raw> --chapters 1-3  # several, one session and page each
python3 -m kb_distillery.ingest full-digest <raw> --all           # every undigested chapter
python3 -m kb_distillery.ingest full-digest <raw> --section 2.3   # an outline entry, resolved to its chapter
```

Write the book page's Overview by hand. `finalize` writes the `type: part` page and ticks its row.
Code that works per chapter reads `kb_distillery.vault.books.chapters(root, raw)` and resolves
selectors with `books.select(rows, "1-3")`.

**The chapters table is the truth** (`src/kb_distillery/vault/books.py`, checked by lint). Errors: a
missing, malformed or duplicate id; an id that changed (a part's `chapter:` differs from the row that
links it); a chapter count that differs from `outline_chapters:` (the count ingest found; a split
chapter counts once); a part whose `chapter:` has no row; a row marked digested whose part page does
not exist; gaps and overlaps. A part's `section_pages:` and `depth` must match its row. Coverage is
digested chapters ÷ chapters (`3 / 11 chapters`, skip rows excluded); below all of them the raw file
is `partial`, warns on every run and counts in `--health` as `partial-books`. The book's `maturity`
follows coverage. Re-digesting a finished chapter is refused. Books from before schema 1.6 had a
`## Partition` table; migration 0016 rewrote it (old part slugs stay as `aliases:`).
