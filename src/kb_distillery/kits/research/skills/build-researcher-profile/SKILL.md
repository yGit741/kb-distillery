---
name: build-researcher-profile
description: >-
  Build or refresh a person page: index the Semantic Scholar bibliography, check every
  handle (homepage, Scholar, GitHub, YouTube, blog feed, Wikipedia), fill roles, lineage and
  open material, catalog star-tier papers only (≥200 cites, ≤10). Use for add researcher,
  build researcher profile, index researcher, person profile, add <name>'s papers. Do NOT
  digest or catalog all papers.
audience: app
mode: write
---

# build-researcher-profile

**LLM tier:** light · **Budget:** ~3–8k tokens (verify step only)

A person page is **handle-driven** (`src/kb_distillery/vault/persons.py`): each frontmatter handle generates one
section, `none` means "checked, there is none" (no section), `unknown` means "checked, not
found", and a *missing* key means not checked yet. `verified: YYYY-MM-DD` is the only progress
marker; `distill lint --health` counts pages without one (`persons-unverified`).

| Handle | Generates | Source |
|---|---|---|
| `wikipedia` | Roles & companies, Academic lineage | Wikidata (employer, founded, doctoral advisor/student) |
| `url` (homepage) | Courses | agent reads the homepage |
| `github` | Repos | top repos by stars |
| `youtube` | Videos & talks | channel / playlist |
| `blog` (feed) | Writing | RSS/Atom; a series page in the vault when one exists |
| `scholar` | Bibliography, Cataloged in vault | Semantic Scholar rows (+ manual rows) |

Edges `orgs`, `advisors`, `students` are bare slugs (`[]` = checked, nobody). Hand-owned:
the intro sentence, `## Why it matters here` (must link a topic or idea), `## Meeting log`,
any custom section — finalize never rewrites them.

## Triggers

- `add researcher <name>`, `build researcher profile`, `index researcher`, `person profile`

## Do NOT

- Run `easy-digest`, `full-digest`, or `deep-digest` in this workflow
- Catalog papers below star tier (citationCount under 200) or mega-author reports (>20 authors) unless pinned
- Auto-download the full bibliography — only up to 10 star-tier PDFs
- Edit the wiki page by hand for generated sections — edit `manifest.json`, then `finalize`
- Guess between namesakes: an ambiguous search exits 2 with the top hits; rerun with `--author-id`

## Phase 1 — begin (0 LLM)

```bash
distill ingest index-researcher begin "<name|scholar-url|ss-author-id>" [--author-id ID] [--slug slug]
```

Creates `meta/.researcher/<slug>/manifest.json` (v2). Re-running on an existing person keeps
the hand-filled items, handles, edges and pin/exclude marks and refreshes the Semantic Scholar rows.

## Phase 2 — verify (agent, required)

One checklist for everyone — skip nothing, record what does not exist as `none`:

1. **Wikipedia/Wikidata** → `handles.wikipedia`; `roles` (`{from, to, org, role, kind}`),
   `lineage` (`{relation: Advisor|Student|Postdoc host, name, slug, where, years, note}`),
   `edges.orgs/advisors/students` (slugs; a slug without a page is listed in health as a stub).
2. **Homepage** → `handles.url`; `courses` (`{title, url, year, note}`); confirm affiliation.
3. **GitHub** → `handles.github`; `repos` (`{title, url, metric, note, action}`), top ~5 by stars.
4. **YouTube** → `handles.youtube`; `videos` (playlists/talks worth a `series-` or `video-` page).
5. **Blog feed** → `handles.blog`; `writing` (key posts; link a `series-` page via `wiki:` when one exists).
6. **Scholar** → compare paper count / top titles with the manifest; `pin: true` a paper the
   citation count undersells, `exclude: true` one that is not really theirs.
7. `verify` block: `scholar_paper_count`, `verified_at`, `agent_notes`; set `verified: YYYY-MM-DD`.

Every item carries `source` (`wikipedia|github|youtube|blog|scholar|manual`) and an optional
`action` (`index` default, `scrap`, `catalog`).

```bash
distill ingest index-researcher verify <slug>     # prints what is still unchecked
```

## Phase 3 — finalize (0 LLM)

```bash
distill ingest index-researcher finalize <slug>
```

Writes `wiki/<slug>.md` — generated sections from the manifest, hand sections preserved — and
catalogs star-tier papers (≤10) to `raw/` with `depth: listed`. Then write
`## Why it matters here` by hand if the page is new.

Semantic Scholar's arXiv id is **verified before download**: the record behind it must name a
known author or share most of the title, else the paper is re-found by title search, else skipped
(`arxiv_mismatch` in the finalize summary — look it up by hand). A downloaded PDF whose page-1
stamp is another id is discarded (`wrong_pdf`). An arXiv outage lists the paper under
`scrap_failed`; run finalize again later.

```bash
distill ingest index-researcher abort <slug>
distill ingest index-researcher status
distill ingest index-researcher relink <slug>     # dangling bibliography links → titles
```

## Output

| Artifact | Content |
|----------|---------|
| Person page | handles + edges frontmatter, generated sections, Why it matters, Meeting log |
| Paper Source pages | ≤10, `depth: listed` only |
| Corpus | Cataloged PDFs as `queued`, `collection` = person slug |

## Quality bar

- `distill lint` passes: every handle a URL/`none`/`unknown`, sections match handles, Why it matters links a topic or idea
- `verified:` set, no `unknown` left that one more search could resolve
- Lineage reciprocal where both pages exist (lint warns otherwise)
- No paper has `depth: easy|full|deep`

## Next step

User picks cataloged or suggested papers for `easy-digest` / `full-digest` explicitly.
