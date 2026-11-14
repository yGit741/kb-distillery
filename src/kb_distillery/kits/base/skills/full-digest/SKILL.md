---
name: full-digest
description: Deepen a Source page to depth full via transactional ingest (~8-12k tokens, medium tier). Use ONLY for "full-digest" or "full digest". Do NOT use for bare "digest", "easy-digest", or "deep-digest".
audience: app
mode: write
---

# full-digest

**LLM tier:** medium · **Budget:** ~8–12k tokens in

Replaces legacy `thesis-ingest`.

## Triggers

- `full-digest`, `full digest`, `read this paper fully`

## Do NOT

- Trigger on bare `digest` — ask tier first
- Trigger on `easy-digest` or `deep-digest`
- Run the paper session on a video (`raw/videos/…/video.md`): a video's full tier is
  `distill ingest video-digest <raw> --tier full` (`.claude/skills/scrap-data/youtube/SKILL.md`)
- Write `wiki/` directly during an open session
- Mark as heavy tier

## Commands

```bash
distill ingest full-digest <raw>   # opens session, prints next steps
distill ingest begin <raw>         # same session API
distill ingest extract <sha>       # fill claims.json — see src/kb_distillery/ingest/extract_prompt.md
distill ingest extract <sha> --fill [--backend subscription|api|batch] [--model sonnet]   # kb_distillery.llm fills it
distill ingest map <sha>
distill ingest draft <sha>
distill ingest finalize <sha>      # lint --ingest-strict for depth full
distill ingest abort <sha>
```

## Agent steps after `begin` / `full-digest`

1. Run `extract` — read `meta/.ingest/<sha>/extracted.text` (the whole document; a book is digested by chapter, `--chapter N`). If
   the raw entity has a `parsed.md` sidecar (e.g. `raw/emails/<YYYY-MM-DD-thread>/parsed.md`),
   `extracted.text` is that sidecar's content instead of raw PDF/thread text.
2. Write `claims.json` with real LaTeX equations, results, ideas — or run `extract <sha> --fill`: `kb_distillery.llm`
   fills the template from `extracted.text` with the same `extract_prompt.md` (Sonnet; `--backend`, default
   `$KB_LLM_BACKEND` then subscription). A reply that fails `validate_claims` goes to `claims.draft.json` and
   claims.json stays the template; a filled claims.json is never replaced. Review the filled claims before `map`.
3. Set `person` when the raw file's corpus `collection` names a person page (researcher bibliography).
4. Re-run `extract` to validate.
5. `map` → `draft` → review `staging/` → `finalize`. Each new `q-` stub in `staging/` needs a short H1 (≤ 80 chars, the question's name) and its formal statement under `## Question` — fill it before `finalize`.

## Many sources at once (backlog)

`distill ingest digest-many` batches the claim-fill for a whole selection (Message Batches, half price), then
runs the sessions one at a time from the cached claims — each source ends in its own `kb(digest)` commit. Resumable
(`.cache/digest-many/<run>/state.json`); never forces a reply that fails `validate_claims` (it lands in `drafts/`).

```bash
distill ingest digest-many submit --run blog --hub series-example-blog --topics comb,prob --dry-run   # count + $ estimate
distill ingest digest-many submit --run blog --hub series-example-blog --topics comb,prob --max-usd 10
distill ingest digest-many collect --run blog [--wait 3600]   # batches take minutes to hours
distill ingest digest-many drive --run blog [--max 10]        # stops after 3 failed sessions in a row
distill ingest digest-many status --run blog
```

Deepening an existing page keeps its frontmatter (`blog`, `created`, `url`, `description`, …) and its `## My notes`; `area`
is never guessed for it, and `open_questions` spawn no `q-` stubs in a bulk run.

## Books (≥60 pages)

A book is digested one **chapter** at a time — never whole. Ingest (`catalog`, or `ingest book <raw>`
for a PDF filed earlier) builds the `book-<stem>` page and its `## Chapters` table first; digest is
refused until it exists. `toc` prints the chapters with their fixed ids:

```bash
distill ingest toc <raw>                          # [x] digested · [ ] backlog · [-] skip
distill ingest full-digest <raw> --chapter 3      # or --chapters 1-3, --all (one session per chapter)
```

The session id is `<sha>-<chapter id>`. `map` names the page `part-<book stem>-<id>-<topic>` with
`type: part` and `chapter: <id>`; `finalize` ticks the chapter's row on the book page.
`claims.json` `title` is the chapter's title. Write the book page's `## Overview` paragraph once —
lint warns until it exists. Rules: `.claude/docs/collections.md` § Books and chapters.

## Course / series rows

A `course-`/`series-` collection's `## Contents` table lists its member raw files. Digest one row by
passing the collection slug (the row's raw files are read together, e.g. slides + handwritten notes):

```bash
distill ingest full-digest course-runi-rl --row 3
```

The page type follows the raw format: `presentations/`, `handwritten/` → `lecture-`;
`emails/` → `mail-`; `web-clips/` or non-PDF `printed-docs/` → `article-` (a tagged blog
post → `blog-`); `printed-docs/` PDF → `paper-`. LLM chats (`llm-chats/`) are not digested here —
they become `chat-` pages through the chat pipeline, which needs their `meta/chats/` tree.
`finalize` ticks the row (`full`) and links the new page. Passing a raw path that is a collection
member auto-scopes to its row.

## Output

A Source page (`layer: source`) at `depth: full`, `maturity: digested`, Key equations required at finalize.
An existing page (e.g. `depth: listed` or `easy`) is deepened in place. For a book: a `type: part`
page plus a ticked chapter row. For a collection row: a Source page plus a ticked Contents row.

## Quality bar

- Key equations: real LaTeX, not `—`
- Ideas link to existing wiki slugs
- topic pages (`theme-*`) `## Papers` updated via finalize
- Person link when the raw file's `collection` names a researcher

## Pitfalls

- The negation-word polarity check is now a warning (score capped at 60): it only fires when a negation sits within a few tokens of topic words the other page asserts, and never between a paper and its own new stubs. Do not reword honest assumptions to silence it; `coherence dismiss <id>` if it is spurious.
- A paper with long appendices (60+ pages) is treated as a paper when it has an abstract and no chapter outline.
- Idea and `q-` stubs are registered with the session automatically (map and finalize), so an aborted finalize removes them and restores topic-page `## Papers` lines; the old `staging/` is kept as `staging-aborted-<time>/`, and `begin` restores `claims.json`/`plan.json` of an aborted session.
- Topic slugs in `claims.json` `concepts` (a protocol key, kept) map to `area:`, not to new idea pages.

## Summary

After finalize, refresh the page's `description:` (schema 1.3): `python3 -m kb_distillery.digest run --slugs <slug>` then `python3 -m kb_distillery.digest apply --slugs <slug>` inside the open ops session — a deeper page always gets a new one; skip pages whose `generated.by` is a `human:<id>`.

## Commit

The CLI commits this operation itself as `kb(digest): … (kb-x.y.z)` on main — only the files it changed (`--no-commit` to skip). Check with `distill ops log -n 1`. `finalize` is the commit point.
