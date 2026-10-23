---
name: query-knowledge
description: Answer questions from the wiki — index-first navigation, citations, optional file-back. Use for query-knowledge, query-kb, query kb, what do I know about, where did I read, compare, explain from my notes. Do NOT answer from memory without searching; raw sources go through explore-raw-data.
---

# query-knowledge

**LLM tier:** light–medium · **Budget:** ~3–15k tokens (index + 3–8 pages)

Karpathy **Query** operation: search the wiki, read pages, synthesize with citations. Good answers can be filed back as new wiki pages.

This is **not** `meta.ingest resolve` (dedup before scrap). This is **reading** the knowledge base.

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
python3 meta/query.py candidates "<question keywords>"
python3 meta/query.py mocs                    # theme- entry points, for broad / thematic questions
python3 meta/lint.py --health                 # optional: orphans, broken links
```

1. **Read `index.md`** — skim the relevant section (themes, questions, papers, concepts).
2. **Run `candidates`** — supplements index with full-text term hits.
3. **Pick 3–8 slugs** — prefer `theme-*` + `q-*` for thesis questions; reading units
   (`paper-`, `part-`, `lecture-`, `article-`, `conversation-`) for citations.
   Old slugs (`moc-…`, unprefixed papers) live in `aliases:` — `python3 -m meta.ingest resolve <old-slug>`.

Never claim “nothing in the vault” until both index and `candidates` were checked.

## Phase 2 — read & synthesize

1. Read selected `wiki/<slug>.md` files (targeted reads, not the whole tree).
2. **Prefer wiki over training knowledge.** Cite with bare wikilinks: `[[tensor-rank]]`.
3. Answer in chat — format as prose, table, or list depending on the question.
4. Note gaps: queued raw, `to-read` papers, open questions (`status: open`).

## Phase 3 — file back (only when asked)

Karpathy: explorations should compound, not die in chat.

| User intent | Where to write |
|-------------|----------------|
| New stable concept | `wiki/<concept-slug>.md` (`type: concept`) |
| New research question | `wiki/q-<slug>.md` (`type: question`) |
| Personal deliberation | `think/*.md` (human-owned; never agent-edit directly) |
| Comparison / analysis worth keeping | concept or question page; cross-link sources |

After filing: `python3 meta/lint.py` and optional `meta/log.md` entry:
`## [YYYY-MM-DD] query | <short title>`

## Entry points for this vault

- **Thesis direction:** `[[theme-info-theory]]`, `[[theme-quantum]]`, `[[theme-tensor-factorization]]`, open `q-*` pages
- **Course provenance:** `course-*` / `series-*` hubs — their `## Contents` table lists every member and its digest
- **Books:** `book-*` / `notebook-*` hubs — `## Partition` links each digested `part-*`
- **Activity:** `meta/log.md`
- **Human scratch:** `think/my-true-research-start-here.md` (read if relevant; do not edit)

## Reaching raw

The wiki is the only thing this skill reads. When a source is needed — a contradiction between
pages, an undigested source relevant to the question, or an explicit request about an undigested
file — invoke `explore-raw-data` (`python3 -m meta.explore_raw find|read|check|recommend …`).
Attribute every raw-derived sentence with the raw path and the reason you opened it.

## Scale note

~1100 pages: **index + candidates is still enough.** If search gets noisy, consider [qmd](https://github.com/tobi/qmd) for hybrid search (optional; not wired yet).

## Commit

Answering is read-only. Filing an answer back is a wiki edit: Wrap any wiki fix in an ops session so it becomes one undoable commit: `pixi run ops -- begin refine <slug> "why"` → edit → `pixi run ops -- commit` (see `wiki-edit`).
