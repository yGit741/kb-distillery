# Page model

> Page layers, depth, frontmatter, prefixes, `## My notes`, person pages, note sections, topic whitelist. Part of the doc router in [`AGENTS.md`](../../AGENTS.md).

## Page layers

Every wiki page has a `layer:` and a `type:` within it (`backend/src/kb/core/schema.py` `LAYER_OF`). Verbs:
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
| `deep` | thesis-critical: full + neighbor papers, q- stubs, topic threads (`deep-digest`) |

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
status: to-read|reading|digested   # sources + collections; idea/topic: seed|growing|solid;
                             # question: open|partial|resolved; distilled-think: review|applied|archived;
                             # scope: active|parked; person: none — see below
depth: listed|easy|full|deep # sources only — listed ⇒ to-read|reading, easy/full/deep ⇒ digested
area: [info-theory]          # topic slugs only (whitelist TOPIC_SLUGS in backend/src/kb/core/schema.py)
summary: "…"                 # one English line, 80–320 chars: what the page is + its main point (schema 1.3)
summary_from: 3f9a1c0b7e21   # hash of H1 + Problem/Main result + Key claims it was written from (stale check)
summary_by: me               # optional: you wrote it — tools never overwrite it
relations:                   # optional typed links to other pages (schema 1.4); see below
  - {to: other-slug, kind: extends, note: "why it holds"}
related: [tensor-rank]       # bare slugs — wiki/ is flat, so no paths
aliases: [old-slug]          # renamed pages keep their old slug; `kb.ingest resolve <old-slug>` finds them
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

**`relations:`** (schema 1.4, `backend/src/kb/graph/relations.py`) — typed links a page states about other pages: `to`
(a slug), `kind` and a `note`. The kinds a knowledge base accepts are its `kb.toml` `[edges] types` (the thesis kb:
extends, uses, contradicts, example-of, open-problem-in, addresses, student-of); `symmetric` kinds (contradicts) are
stored once, and `note_required` kinds need a one-sentence note. Lint errors on an undeclared kind, a missing or
self target, a missing note, a repeated (kind, target), a malformed block, and on a source page that is not depth
`full` or `deep` (a concept page may always state relations). Relations are proposed by `python -m kb.graph.propose`
and applied only after review; the graph reads them behind the `graph-relations` flag.

**`summary:`** (schema 1.3, `backend/src/kb/core/summary.py`) — every page except courses and `listed`
sources carries one English line saying what the page is and its main point, in the same template for
every type, so a short idea and a long post are equally searchable. It feeds `index.md`, search cards and
embeddings. Sonnet writes it (`pixi run summarize -- run --slugs <slug>`, then `apply` inside an ops
session); `summary_from` lets lint warn when the page's point changed since. A page that gets deeper is
re-summarized; edits to links, Connections or typos never are. Lint: malformed → error, missing → one
aggregated warning (until the backfill ends), stale → warning; `summary_by: me` pages are never rewritten.

**`## My notes`** — every concept page (idea, topic, question, person) ends with a reserved
`## My notes` section that is the user's: no tool overwrites it and it stays last
(`backend/src/kb/core/wikiio.py`); lint warns when a page has two or it is not last. Agents never write in it.

**Person pages are handle-driven** (`backend/src/kb/core/persons.py`, schema 0.12). Frontmatter holds only
handles, edges, contact and a date (besides `type: person`, `layer: concept`) — no `status`, `area`, `related` or `affiliation`:

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
non-reciprocal `advisors`/`students`. See `skills/build-researcher-profile/SKILL.md`.


## Note sections

Sources:
- **paper** — Setup & assumptions → Proof idea (sketch only) → Key equations → Takeaways for my thesis → Connections → Links out (`meta/templates/paper.md`; at `depth: listed` it holds only **Problem:** / **Main result:** lines)
- **part** — as paper, plus a `> Part of [[book]] · pp. A–B` line under the title
- **lecture** — `> Lecture of [[course]]` line → Setup & assumptions → Key equations → Takeaways for my thesis → Connections → Links out
- **article / mail** — Key claims → Key equations → Takeaways for my thesis → Connections → Links out (mail = an email thread)
- **ai-chat** — rendered from its `meta/chats/` tree by the chat pipeline (`conversation:` names the tree)
- **blog-post** — rendered by `backend/src/kb/ingest/blog.py`: Blog Post Summary → Key concepts → Post
- **video** — Key ideas → Key equations → Takeaways for my thesis → Connections → Links out

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
