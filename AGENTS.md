# Thesis Wiki — agent schema

Personal knowledge base for an MSc in theoretical ML. **The thesis topic is not yet chosen** — the vault exists to explore candidate directions and decide. Follows the [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern.

## Layers

| Layer | Path | Rule |
|-------|------|------|
| **Raw** | `raw/` | User-owned inputs. **Immutable — never write here.** |
| **Wiki** | `wiki/` | Agent-owned synthesis. Flat. Create, update, cross-link. |
| **Meta** | `meta/` | Schema, templates, log. |

```
raw/inbox/            reMarkable sync target. Any shape. MUST drain to zero.
raw/papers/<course>/  academic PDFs
raw/slides/<course>/  lecture decks, presentations
raw/notes/<course>/   handwritten notes, recaps, scratch
raw/web/  raw/assets/ clips, images (flat)
wiki/                 every note, flat. q- = question, moc- = map of content
_quarantine/          staged for deletion, gitignored, not part of the vault
```

## meta/lint.py IS the schema

Prose rules drift; this doesn't. If `python3 meta/lint.py` passes, the write is legal.

```
python3 meta/lint.py                 check + reconcile the manifest
python3 meta/lint.py --health        dashboard: inbox, backlog, drift, links
python3 meta/lint.py --pending       the ingestion backlog
python3 meta/lint.py --write-index   regenerate index.md
```

`meta/guard.py` runs as a PreToolUse hook and blocks illegal writes before they happen. `.git/hooks/pre-commit` runs the linter. Do not hand-edit `index.md` or `meta/corpus.tsv` — both are generated.

## Frontmatter

```yaml
type: concept | question | person | paper | source | moc
status: seed|growing|solid   (question: open|partial|resolved; paper: to-read|reading|digested)
area: [info-theory]          # moc slugs, bare
related: [tensor-rank]       # bare slugs — wiki/ is flat, so no paths
raw: raw/papers/x/y.pdf      # paper/source only; `none` + a `url:` if read externally
```

Wikilinks are always bare: `[[tensor-rank]]`, never `[[concepts/tensor-rank]]`. Paths into `raw/` go in backticks, not wikilinks.

## The corpus manifest

`meta/corpus.tsv` has one row per file in `raw/`. Nothing can be silently forgotten.

| disposition | meaning |
|-------------|---------|
| `queued` | keep, not yet written up — **the real backlog** |
| `digested` | a wiki page cites it via `raw:` |
| `skip` | explicitly not worth a note (a decision, not neglect) |
| `dupe:<path>` | superseded by another file |
| `ink:<path>` | reMarkable annotation overlay belonging to `<path>` |

The linter maintains it: a new file appears as `queued`; a file gone from disk is removed; **a sha1 change on a `digested` file re-opens it as `queued`** — so re-annotating a paper on the tablet automatically re-queues it.

## Naming

`raw/papers/` uses **`<year>-<kebab-title>.pdf`** — lowercase, hyphens, no spaces. Sortable, greppable, and the year is metadata you would otherwise have to open the file to find.

```
2023-toolformer.pdf
1948-a-mathematical-theory-of-communication.pdf
```

The linter enforces the pattern and cross-checks the filename year against the digest's `year:` frontmatter, so the two cannot drift apart. Only `raw/papers/` is held to this: handwritten notes and lecture decks keep their original names, which are provenance.

⚠️ reMarkable's `X (annotations).pdf` exports are **ink-only overlays**, not annotated documents — typically a few KB against a multi-MB source, and unreadable on their own. They have all been deleted. If new ones appear, do not delete the source document in their favour.

## Note sections

- **concept** — One-liner → Intuition → Formal → Why it matters → Connections → Open questions
- **question** — Question → Why it matters → What would answer it → Current state → Links
- **paper** — Problem → Method → Result → Why it matters here → Connections
- **moc** — Scope → Key concepts → Raw material → Threads

## Workflow

**Ingest (transactional):** one paper at a time via `python3 -m meta.ingest`.

```
begin <raw_path>     open session, backup existing digest
extract <sha>        PDF text + validate claims.json (agent fills claims — see meta/ingest/extract_prompt.md)
map <sha>            plan.json: concepts → wiki slugs, MOC targets, q- stubs
draft <sha>          render markdown to meta/.ingest/<sha>/staging/ only
finalize <sha>       promote to wiki/, patch MOCs, lint --ingest-strict; rollback on fail
abort <sha>          restore backups
status | backlog     session list / queued papers
```

During an open session, `meta/guard.py` blocks direct writes to wiki paths the session owns — use `draft` + `finalize`. Session state lives in `meta/.ingest/` (gitignored).

**Manual ingest (legacy):** read the raw file → write one `wiki/` page with a `raw:` field → run the linter → append to `meta/log.md`. Prefer the transactional pipeline for papers.

**Triage:** anything in `raw/inbox/` gets moved to a kind folder or deleted. The inbox is a queue, not storage.

**Query:** read `index.md` first, then follow wikilinks.
