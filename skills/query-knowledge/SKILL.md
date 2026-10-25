---
name: query-knowledge
description: Answer questions from the wiki — index-first navigation, citations, optional file-back. Use for query-knowledge, query-kb, query kb, what do I know about, where did I read, compare, explain from my notes. Do NOT answer from memory without searching; raw sources go through explore-raw-data.
---

# query-knowledge

**LLM tier:** light–medium · **Budget:** ~3–15k tokens (index + 3–8 pages)

Karpathy **Query** operation: search the wiki, read pages, synthesize with citations. Good answers can be filed back as new wiki pages.

This is **not** `kb.ingest resolve` (dedup before scrap). This is **reading** the knowledge base.

## Triggers

- `query-knowledge` (aliases `query-kb`, `query kb`), `search the vault`, `what do I know about …`
- Any question that should be answered **from this wiki first**, not from training data

## Do NOT

- Answer from memory when the vault may have pages — search first
- Ingest or write wiki pages unless the user asks to **file** the answer
- Open `raw/` files directly — reach sources only through `explore-raw-data`
- Confuse with `resolve` (ingest dedup) or `distill` (think → wiki propagate)

## Phase 1 — locate (0 LLM via CLI)

```bash
python3 -m kb.search.query candidates "<question keywords>"
python3 -m kb.search.query mocs                    # topic pages (theme-*) as entry points, for broad questions
python3 -m kb.lint.lint --health                 # optional: orphans, broken links
```

1. **Read `index.md`** — skim the relevant section (topics, questions, sources, ideas).
2. **Run `candidates`** — supplements index with full-text term hits.
3. **Pick 3–8 slugs** — prefer topic pages (`theme-*`) + `q-*` for thesis questions; Source pages
   (`paper-`, `part-`, `lecture-`, `article-`, `mail-`, `chat-`) for citations.
   Old slugs (pre-`theme-` topic slugs, unprefixed papers) live in `aliases:` — `python3 -m kb.ingest resolve <old-slug>`.

Never claim “nothing in the vault” until both index and `candidates` were checked.

## Phase 2 — read & synthesize

1. Read selected `wiki/<slug>.md` files (targeted reads, not the whole tree).
2. **Prefer wiki over training knowledge.** Cite with bare wikilinks: `[[tensor-rank]]`.
3. Answer in chat — format as prose, table, or list depending on the question.
4. Note gaps: queued raw, `to-read` papers, open questions (`status: open`).

## Scoped questions

A **scope** is a personal set of raw files (`/scopes`, `scope-*` page); its knowledge is a projection:
the pages citing those files plus the ideas/questions at least two of them link. When the user asks
"in scope scope-x …" (or the chat's Scope select is set), answer **only from that projection**.

```bash
python3 -m kb.search.query scope-status scope-x                    # title, coverage, page list, undigested files
python3 -m kb.search.query candidates "<keywords>" --scope scope-x # rank within the scope's pages only
```

1. Run `scope-status` first; the page list is the whole universe for this answer.
2. Locate with `candidates … --scope scope-x`, read 3–8 of those pages, cite only them as `[[slug]]`.
3. If the scope's pages do not cover the question, say so — do not borrow from other pages or from general knowledge.
4. **End every answer with** `Not yet digested in this scope: <uncovered files>` (from `scope-status`,
   `NOT_YET_DIGESTED`); offer `explore-raw-data` (`find … --scope scope-x`) to look at them.
5. Unknown scope → the command exits 2 with the known scopes; ask which one is meant.

## Phase 3 — file back (only when asked)

Karpathy: explorations should compound, not die in chat.

| User intent | Where to write |
|-------------|----------------|
| New stable idea | `wiki/<idea-slug>.md` (`type: idea`, `layer: concept`) |
| New research question | `wiki/q-<slug>.md` (`type: question`) |
| Personal deliberation | `think/*.md` (human-owned; never agent-edit directly) |
| Comparison / analysis worth keeping | idea or question page; cross-link sources |

After filing: `python3 -m kb.lint.lint` and optional `meta/log.md` entry:
`## [YYYY-MM-DD] query | <short title>`

## Entry points for this vault

- **Thesis direction:** `[[theme-info-theory]]`, `[[theme-quantum]]`, `[[theme-tensor-factorization]]`, open `q-*` pages
- **Course provenance:** `course-*` / `series-*` collections — their `## Contents` table lists every member and its digest
- **Books:** `book-*` / `notebook-*` collections — `## Partition` links each digested `part-*`
- **Activity:** `meta/log.md`
- **Human scratch:** `think/my-true-research-start-here.md` (read if relevant; do not edit)

## Reaching raw

The wiki is the only thing this skill reads. When a source is needed — a contradiction between
pages, an undigested source relevant to the question, or an explicit request about an undigested
file — invoke `explore-raw-data` (`python3 -m kb.search.explore_raw find|read|check|recommend …`).
Attribute every raw-derived sentence with the raw path and the reason you opened it.

## Scale note

~1100 pages: **index + candidates is still enough.** If search gets noisy, consider [qmd](https://github.com/tobi/qmd) for hybrid search (optional; not wired yet).

## Commit

Answering is read-only. Filing an answer back is a wiki edit: Wrap any wiki fix in an ops session so it becomes one undoable commit: `pixi run ops -- begin refine <slug> "why"` → edit → `pixi run ops -- commit` (see `wiki-edit`).
