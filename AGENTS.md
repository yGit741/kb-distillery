# Thesis ML Wiki — Agent Schema

Personal knowledge base for theoretical ML thesis work (complex-valued NNs, implicit regularization, tensor factorization). Follows the [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern.

## Three layers

| Layer | Path | Rule |
|-------|------|------|
| **Raw** | `raw/` | Immutable sources. **Read only — never edit.** |
| **Wiki** | everything else | LLM-owned synthesis. Create, update, cross-link. |
| **Schema** | this file | Conventions and workflows. Co-evolve with the user. |

## Directory map

```
raw/papers/       PDFs, arXiv originals
raw/articles/     blogs, Substack, web clips (markdown)
raw/notes/        meeting memos, lecture notes, handwriting scans
raw/assets/       images downloaded from clipped articles
concepts/         technical definitions and intuition
questions/        open research questions
people/           researchers (entities)
papers/           per-paper digests (linked to raw/papers/)
sources/          per-source summaries (articles, talks — linked to raw/)
moc/              Maps of Content — topic hubs
meta/             thesis-level metadata
templates/        note templates (do not ingest as wiki pages)
index.md          master catalog — update on every ingest
log.md            append-only activity timeline
00-home.md        human-facing overview / entry point
```

## Page types & frontmatter

All wiki pages use YAML frontmatter. Wikilinks: `[[path/without-extension|display]]`.

### concept (`concepts/`)
```yaml
type: concept
area: [complex-nn]          # MOC slugs
status: seed | growing | solid
sources: [sources/foo]      # source digest pages that informed this
related: [tensor-rank]      # other concept slugs (no path prefix)
```

Sections: One-liner → Intuition → Formal → Why it matters (thesis angle) → Connections → Open questions.

### question (`questions/`)
```yaml
type: question
area: []
status: open | partial | resolved
priority: low | med | high
```

### paper (`papers/`)
```yaml
type: paper
authors: []
year:
area: []
status: unread | reading | digested
citekey:
url:
raw: raw/papers/foo.pdf     # path into raw/ (required once ingested)
```

### source (`sources/`) — Karpathy "sources" layer for non-paper raw files
```yaml
type: source
raw: raw/articles/foo.md    # required
format: article | talk | notes
area: []
status: digested
```

### person (`people/`)
```yaml
type: person
role: thesis-instructor | researcher | ...
optional: true              # mark optional contacts
```

### moc (`moc/`)
Topic hub listing concepts, questions, papers, thesis threads for one area.

## Naming

- Files: lowercase, hyphenated (`tensor-factorization.md`)
- One primary concept per file; split when scope grows
- Paper files: short slug from title or citekey

## Workflows

### Ingest

User drops file into `raw/` and says e.g. *"Ingest `raw/papers/cohen-expressivity.pdf`"*.

1. Read the raw file. **Do not modify `raw/`.**
2. Discuss key takeaways with user if non-obvious.
3. Create or update wiki pages:
   - `sources/<slug>.md` or `papers/<slug>.md` (digest)
   - Relevant `concepts/`, `questions/`, `people/`
   - Link from relevant `moc/`
4. Set `sources:` / `raw:` frontmatter links on updated pages.
5. Update `index.md` (add or revise one-liner).
6. Append entry to `log.md`:
   ```
   ## [YYYY-MM-DD] ingest | <title>
   - Raw: `raw/...`
   - Created: [[sources/...]], [[concepts/...]]
   - Updated: [[concepts/...]], [[moc/...]]
   ```

A single source often touches 5–15 wiki pages.

### Query

User asks a research question.

1. Read `index.md` first to find relevant pages.
2. Read those pages; synthesize with citations to wiki pages and raw paths.
3. If the answer is reusable (comparison, analysis, connection), **file it back** as a new concept, question, or moc section — do not leave it only in chat.
4. Append `## [YYYY-MM-DD] query | <short topic>` to `log.md`.

### Lint

User says *"Lint the wiki"* (or run periodically).

Check and report:
- Contradictions between pages
- Stale claims superseded by newer sources
- Orphan pages (no inbound wikilinks)
- Concepts mentioned without own page
- Missing cross-references between related concepts
- `sources:` frontmatter empty on `status: solid` concepts
- Questions with `status: open` but no linked reading list

Propose fixes; apply after user confirms.

### New note (manual)

1. Pick template from `templates/`.
2. Place in correct folder.
3. Link from relevant `moc/` and `00-home.md` if prominent.
4. Add to `index.md`.

## Status progression

| Type | Flow |
|------|------|
| concept | `seed` → `growing` → `solid` (can explain without source open) |
| paper | `unread` → `reading` → `digested` |
| question | `open` → `partial` → `resolved` |

## Thesis context

- **Topic:** Theoretical ML — complex-valued NNs, implicit regularization, tensor factorization
- **Instructor:** [[people/nadav-cohen]] (optional)
- **Meta:** [[meta/thesis]]

Prefer connections to thesis threads over generic ML summaries.

## Obsidian

- Vault root is this directory.
- Graph view for connectivity; MOCs for navigation.
- Optional: set attachment folder to `raw/assets/`.

## Do not

- Edit anything under `raw/`
- Delete wiki pages without user approval
- Create duplicate concept pages — merge and redirect links
- Skip `index.md` / `log.md` updates on ingest
