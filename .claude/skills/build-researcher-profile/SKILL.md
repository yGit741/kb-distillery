---
name: build-researcher-profile
description: >-
  Index full researcher bibliography (Semantic Scholar) and catalog star-tier
  papers only (≥200 cites, max 10). Use for build researcher profile, index
  researcher. Do NOT digest or catalog all papers.
---

# build-researcher-profile

**LLM tier:** light · **Budget:** ~3–8k tokens (verify step only)

Index all papers on a person page; catalog only influential (⭐) papers as PDF stubs. Never digest in this workflow.

## Triggers

- `build researcher profile`, `index researcher`, `researcher profile`

## Do NOT

- Run `easy-digest`, `full-digest`, or `deep-digest` in this workflow
- Catalog papers below star tier (citationCount under 200)
- Auto-download the full bibliography — only up to 10 star-tier PDFs
- Edit `manifest.json` paths without running `finalize` after verify

## Phase 1 — begin (0 LLM)

```bash
python3 -m meta.ingest index-researcher begin "<name|scholar-url|ss-author-id>"
```

Creates `meta/.researcher/<slug>/manifest.json` from Semantic Scholar API.

## Phase 2 — verify (agent, required)

1. Fetch Google Scholar profile + personal homepage (web fetch).
2. Compare paper counts / top titles vs manifest.
3. Edit `meta/.researcher/<slug>/manifest.json`:
   - `books` — title, year, url, note (index only, no PDF)
   - `courses` — title, url, note
   - `verify` — `scholar_paper_count`, `verified_at`, `agent_notes`
   - optional: `research_themes`, `related` concept slugs
4. Optionally save HTML snapshots to session dir.

```bash
python3 -m meta.ingest index-researcher verify <slug>
```

## Phase 3 — finalize (0 LLM)

```bash
python3 -m meta.ingest index-researcher finalize <slug>
```

Writes `wiki/<slug>.md` and catalogs star-tier papers (≤10) to `raw/papers/<slug>/` with `digestion-status: catalog`.

```bash
python3 -m meta.ingest index-researcher abort <slug>
python3 -m meta.ingest index-researcher status
```

## Output

| Artifact | Content |
|----------|---------|
| Person page | Full bibliography + books + courses |
| Paper stubs | ≤10 catalog-tier nodes only |
| Corpus | Cataloged PDFs as `queued` |

## Quality bar

- Person page lists all SS papers with tier emoji
- ≤10 papers have `raw:` + `digestion-status: catalog`
- No paper has `digestion-status: full|easy|deep`
- `verify.agent_notes` documents Scholar/homepage sanity check

## Next step

User picks cataloged or suggested papers for `easy-digest` / `full-digest` explicitly.
