---
name: full-digest
description: Standard paper note via transactional ingest (~8-12k tokens, medium tier). Use ONLY for "full-digest" or "full digest". Do NOT use for bare "digest", "easy-digest", or "deep-digest".
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
python3 -m meta.ingest full-digest <raw>   # opens session, prints next steps
python3 -m meta.ingest begin <raw>         # same session API
python3 -m meta.ingest extract <sha>       # fill claims.json — see meta/ingest/extract_prompt.md
python3 -m meta.ingest map <sha>
python3 -m meta.ingest draft <sha>
python3 -m meta.ingest finalize <sha>      # lint --ingest-strict for digestion-status full
python3 -m meta.ingest abort <sha>
```

## Agent steps after `begin` / `full-digest`

1. Run `extract` — read `meta/.ingest/<sha>/extracted.text` (first 25 pages). If
   the raw entity has a `parsed.md` sidecar (e.g. `raw/mail/<thread>/parsed.md`),
   `extracted.text` is that sidecar's content instead of raw PDF/thread text.
2. Write `claims.json` with real LaTeX equations, results, concepts.
3. Set `person` from `raw/papers/<person>/…` when applicable.
4. Re-run `extract` to validate.
5. `map` → `draft` → review `staging/` → `finalize`.

## Books (≥60 pages)

A book is digested one **part** at a time — never whole. `toc` prints the book's partition
(or a proposed one if the book has no `type: book` page yet):

```bash
python3 -m meta.ingest toc <raw>                     # [x] digested · [ ] backlog · [-] skip
python3 -m meta.ingest full-digest <raw> --part N    # a row; --pages A-B carves a new one
```

The session id is `<sha>-p<A>-<B>`. `map` names the page `<book-slug>-<topic>` with
`type: part`; `finalize` ticks the row on the book page (creating it on the first part).
`claims.json` `title` is the part's title; set `book_title` too when the book page is new.
After the first part, write the book page's `## Overview` paragraph — lint warns until it exists.

## Output

`digestion-status: full`, `status: digested`, Key equations required at finalize.
For a book: a `type: part` page plus an updated `type: book` partition row.

## Quality bar

- Key equations: real LaTeX, not `—`
- Concepts link to existing wiki slugs
- MOC `## Papers` updated via finalize
- Person link when raw is under researcher folders

## Commit

The CLI commits this operation itself as `kb(digest): … (kb-x.y.z)` on main — only the files it changed (`--no-commit` to skip). Check with `pixi run ops -- log -n 1`. `finalize` is the commit point.
