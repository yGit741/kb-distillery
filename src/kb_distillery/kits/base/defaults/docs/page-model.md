# Page model

> Page layers, depth, frontmatter, prefixes, `## My notes`, person pages, note sections, topic whitelist. Part of the doc router in [`AGENTS.md`](../../../../../../AGENTS.md).

## Page layers

Every wiki page has a `layer:` and a `type:` within it (`src/kb_distillery/vault/schema.py` `LAYER_OF`). Verbs:
**Add** (scrap into `raw/inbox/`) → **Catalog** (file the raw item, create its Source page at
`depth: listed`) → **Digest** (deepen that same page in place: easy, full, deep).

| Layer | Types | What it is |
|-------|-------|------------|
| **source** | paper, part, lecture, article, video, mail, ai-chat, blog-post | the digest of one raw item, faithful to it; carries `depth:` |
| **collection** | book, notebook (page partition table) · course, series (Contents table) · aux `scope` | a table grouping sources |
| **concept** | idea, topic, question, person · aux `distilled-think` | knowledge across sources; ends with `## My notes` |

`depth:` (sources only, ordered) — what each depth means, and which depths each source type reaches:

| depth | means |
|-------|-------|
| `listed` | cataloged stub, not read yet |
| `easy` | abstract skim: Problem / Main result only (`easy-digest`, Haiku) |
| `full` | full note with Key equations (`full-digest`) |
| `deep` | deep: full + neighbor papers, q- stubs, topic threads (`deep-digest`) |

| source type | reaches | usually |
|-------------|---------|---------|
| paper | listed · easy · full · deep | any of the four |
| part | full · deep (created by a scoped book digest) | full |
| lecture | full · deep (created from a course row) | full |
| blog-post | listed · easy · full | easy |
| article | easy · full | easy |
| mail, ai-chat | easy · full | easy |
| video | easy · full | easy or full |

Retired names (schema 1.0, no read compatibility — lint errors and names the replacement):
`type: theme` → `topic`, `type: concept` → `idea`, `digestion-status` → `depth`, depth `catalog` →
`listed`, disposition `digested` → `source`; "hub" → collection, "MOC" → topic page, "reading
unit" → source.

## Frontmatter

```yaml
type: <type>                 # see Page layers
layer: source|collection|concept   # right after type:, must match the type
title: "Page title"          # OKF `title`, written only when it differs from the first heading (lint warns on a title that does
                             # differ); omitted otherwise: every reader falls back to the heading (`vault.frontmatter.page_title`)
maturity: to-read|reading|digested   # was `status` (schema 1.5); sources + collections; idea/topic: seed|growing|solid;
                             # question: open|partial|resolved; distilled-think: review|applied|archived;
                             # scope: active|parked; person: none — see below
status: draft                # OKF lifecycle, only `draft`, only on a source at `depth: listed`; omitted otherwise
created: 2026-10-08T00:00:00Z  # was `date`; an ISO 8601 datetime with a UTC offset
depth: listed|easy|full|deep # sources only — listed ⇒ to-read|reading, easy/full/deep ⇒ digested
area: [info-theory]          # topic slugs only (whitelist TOPIC_SLUGS in src/kb_distillery/vault/schema.py)
description: "…"             # was `summary`; one English line, 80–320 chars: what the page is + its main point
summary_from: 3f9a1c0b7e21   # hash of H1 + Problem/Main result + Key claims it was written from (stale check)
generated: {by: summarize/sonnet}   # who wrote the description (OKF §5.2); `at` is allowed (an ISO datetime with a UTC offset) but tools do not write it
                             # `by: human:<id>` (the id is kb.toml `[kb] owner`) = you wrote it — tools never overwrite it
sources: [{resource: paper-x.md}, {resource: https://…}]   # objects with a `resource`: a wiki page path, a plain descriptor such as
                             # `think:<note>.md`, or the Source page's own http(s) `url` next to other entries; never a path into
                             # raw/ or think/. Omitted when it would only repeat `url:` (readers use `vault.frontmatter.resources`)
relations:                   # optional typed links to other pages (schema 1.4); see below
  - {to: other-slug, kind: extends, note: "why it holds"}
related: [tensor-rank.md]    # page paths (vault.links.page_path); wiki/ is the OKF bundle root and is flat
aliases: [old-slug]          # renamed pages keep their old slug; `kb_distillery.ingest resolve <old-slug>` finds them
raw: raw/printed-docs/y.pdf  # sources + book/notebook (a list for multi-file lectures); `none` + a `url:` if read externally
book_pages: 419              # book/notebook only — total PDF pages
book: <book-slug>            # part only — its collection; plus section: and section_pages: A-B
course: <course-slug>        # lecture — its collection
short: rl                    # course/series — filename prefix of its raw members
institution: runi            # course only, plus course_code:, semester:, lecturer:
```

| Prefix | Type (layer) | Prefix | Type (layer) |
|--------|------|--------|------|
| `paper-` | paper (source) | `book-` | book (collection; long PDF) |
| `part-` | part (source; `part-<book stem>-<topic>`) | `notebook-` | notebook (collection; long handwritten PDF) |
| `lecture-` | lecture (source) | `course-` | course (collection; `course-<institution>-<name>`) |
| `article-` | article (source; web clip, tutorial) | `series-` | series (collection; `series-<author>-<name>`) |
| `blog-` | blog-post (source) | `scope-` | scope (collection, aux) |
| `video-` | video (source) | `theme-` | topic (concept) — exactly the 10 TOPIC_SLUGS |
| `mail-` | mail (source; email thread) | `q-` | question (concept) |
| `chat-` | ai-chat (source; LLM chat) | *(bare)* | idea, person (concept) |
| `distilled-think-` | distilled-think (concept, aux) | | |

**`relations:`** (schema 1.4, `src/kb_distillery/graph/relations.py`) — typed links a page states about other pages: `to`
(a slug), `kind` and a `note`. The kinds a knowledge base accepts are its `kb.toml` `[edges] types` (the thesis kb:
extends, uses, contradicts, example-of, open-problem-in, addresses, student-of); `symmetric` kinds (contradicts) are
stored once, and `note_required` kinds need a one-sentence note. Lint errors on an undeclared kind, a missing or
self target, a missing note, a repeated (kind, target), a malformed block, and on a source page that is not depth
`full` or `deep` (a concept page may always state relations). Relations are proposed by `python -m kb_distillery.graph.propose`
and applied only after review; the graph reads them behind the `graph-relations` flag.

**`description:`** (schema 1.3 as `summary:`, renamed in 1.5, `src/kb_distillery/vault/summary.py`) — every page except courses and `listed`
sources carries one English line saying what the page is and its main point, in the same template for
every type, so a short idea and a long post are equally searchable. It feeds the section indexes (`wiki/<type>/index.md`), search cards and
embeddings. Sonnet writes it (`pixi run summarize -- run --slugs <slug>`, then `apply` inside an ops
session); `summary_from` lets lint warn when the page's point changed since. A page that gets deeper is
re-summarized; edits to links, Connections or typos never are. Lint: malformed → error, missing → one
aggregated warning (until the backfill ends), stale → warning; pages whose `generated.by` is a `human:<id>` are never rewritten.

**`## My notes`** — every concept page (idea, topic, question, person) ends with a reserved
`## My notes` section that is the user's: no tool overwrites it and it stays last
(`src/kb_distillery/vault/wikiio.py`); lint warns when a page has two or it is not last. Agents never write in it.

**Person pages are handle-driven** (`src/kb_distillery/vault/persons.py`, schema 0.12). Frontmatter holds only
handles, edges, contact and a date (besides `type: person`, `layer: concept`, `description`; `title` only when it differs from the first heading) — no `maturity`, `status`, `area`, `related` or `affiliation`:

```yaml
url: https://…        # homepage      ⇒ ## Courses
scholar: https://…    # Scholar       ⇒ ## Bibliography, ## Cataloged in vault
github: none          # ⇒ ## Repos            none = checked, there is none (no section)
youtube: unknown      # ⇒ ## Videos & talks   unknown = checked, not found; a missing key = not checked
blog: https://…       # feed          ⇒ ## Writing
wikipedia: https://…  # Wikidata      ⇒ ## Roles & companies, ## Academic lineage
email: …              # contact, no section
orgs: [..] advisors: [..] students: [..]    # bare slugs; [] = checked, nobody
verified: 2026-10-21  # set by finalize; pages without it are the `persons-unverified` backlog
```

Each generated heading carries `<!-- from: <handle|manual> -->` and is rewritten by
`index-researcher finalize` from `meta/.researcher/<slug>/manifest.json`; `## Why it matters
here` (must link a topic or idea), `## Meeting log`, `## My notes` and custom sections are hand-owned and
never touched. Lint enforces the handle ⇒ section rules on verified pages and warns on
non-reciprocal `advisors`/`students`. See `.claude/skills/build-researcher-profile/SKILL.md`.


## Links

Pages link with standard relative markdown links (Open Knowledge Format v0.2; `wiki/` is the bundle root and is flat):
`[Title](slug.md)`, `[label](slug.md#heading)`. The text is the page title (or a label you choose), the target is
`vault.links.page_path(slug)`: writers call `links.link(slug, label)` / `links.page_link(slug, titles)`, never build the
string by hand. Wikilinks (`[[slug]]`) survive only inside the user's `## My notes`, which no tool rewrites; readers
(graph, backlinks, search) read both forms. Lint fails on a wikilink outside My notes (code, math and HTML comments are
not read), on a link to no page, on a heading the target lacks, and on a path (`wiki/x.md`). `[[]]` stays a
harmless empty placeholder. Schema 1.5 moved every page to this form (migration `0014_okf_links`).

**Reserved files (schema 1.5).** `wiki/` is the OKF bundle root, and OKF reserves two files in it: `wiki/index.md` and
`wiki/log.md`. They are not pages: no `type`, no frontmatter rules, never scanned, linted as pages, graphed, searched,
counted, shared as nodes or restored by undo. `index.md` is generated on every lint run (frontmatter holds only
`okf_version: 0.2`; wikilinks in it are a lint error). It is a **tiny root**: one line per page type with the page count
and a one-line description, linking `<type>/index.md`. OKF allows an `index.md` in any directory, so each type has a
generated section index `wiki/<type>/index.md` (rows `- [Title](../slug.md) — summary`, summary cut at 110 characters),
and a type whose section would exceed 40 KB (`vault/wikiindex.py` `SECTION_MAX_BYTES`, e.g. 700 blog posts) splits one
level further, `wiki/<type>/<year>/index.md` (`../../slug.md`; the year is the page's `year`, else `created`, else
`undated`), the type index then listing the years. Every one of these files is a reserved file by its basename. A section
folder holds only its generated `index.md` (lint warns on anything else and removes the ones that no longer apply; it
never touches other files). To find a page: read `wiki/index.md`, then the one section you need, never all of them. `log.md` is the append-only activity timeline: no frontmatter, `# Log`, one
`## YYYY-MM-DD` heading per day (newest day first) and under it that day's entries, newest first, each
`### <op> | <summary>` plus ` ← ` and the backticked targets when it has any; `kb_distillery.vault.log` is its only writer.
`okf-check` (the blocking OKF gate, see `lifecycle.md`) does not count them as pages and needs no `type` from them. Migration `0015_okf_index_log` moved both from `index.md` and `meta/log.md`; a root `index.md` is never written again.

## Note sections

Sources:
- **paper** — Setup & assumptions → Proof idea (sketch only) → Key equations → Takeaways → Connections → Links out (`meta/templates/paper.md`; at `depth: listed` it holds only **Problem:** / **Main result:** lines)
- **part** — as paper, plus a `> Part of [Book title](book-slug.md) · pp. A–B` line under the title
- **lecture** — `> Lecture of [Course title](course-slug.md)` line → Setup & assumptions → Key equations → Takeaways → Connections → Links out
- **article / mail** — Key claims → Key equations → Takeaways → Connections → Links out (mail = an email thread)
- **ai-chat** — rendered from its `meta/chats/` tree by the chat pipeline (`conversation:` names the tree)
- **blog-post** — rendered by `src/kb_distillery/ingest/sources/web/blog.py`: Blog Post Summary → Key concepts → Post
- **video** — Key ideas → Key equations → Takeaways → Connections → Links out

Collections (tables of sources, never sources themselves):
- **book / notebook** — Overview (≥1 paragraph, required) → Partition → Key concepts → Threads
- **course / series** — Overview (≥1 paragraph) → Contents → Threads

Concepts (generated sections first, then `## My notes`, always last):
- **idea** — One-liner → Intuition → Formal → Why it matters → Connections → Open questions → My notes
- **topic** — Scope → Key concepts → Threads → Papers → My notes (research topics only; one per TOPIC_SLUGS entry)
- **question** — Question → Why it matters → What would answer it → Current state → Links → My notes. The H1 is the question's short **name** (≤ 80 chars, lint errors; > 60 warns) and `## Question` holds the formal statement (required, schema 1.1)
- **person** — generated handle sections + hand-owned Why it matters here / Meeting log → My notes
- **distilled-think** — Summary (review prose) → Proposed propagation → Not promoting (transient; use `--cleanup` after apply)

Templates for every type: `meta/templates/<type>.md`.

## Topic whitelist (`area:`)

`statistics`, `optimization-theory`, `learning-theory`, `info-theory`, `implicit-regularization`, `tensor-factorization`, `complex-nn`, `quantum`, `boolean-analysis`, `fourier-analysis` (`TOPIC_SLUGS`). Each has exactly one topic page `theme-<slug>` (`type: topic`). Courses are `course-*` collections, not topics.
