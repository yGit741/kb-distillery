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

⚠️ reMarkable's `X (annotations).pdf` is an **ink-only overlay**, not the annotated document. It is typically a few KB against a multi-MB source. Never delete the source in favour of the overlay. An overlay of ≤700 bytes is a blank page — no annotation at all.

## Note sections

- **concept** — One-liner → Intuition → Formal → Why it matters → Connections → Open questions
- **question** — Question → Why it matters → What would answer it → Current state → Links
- **paper** — Problem → Method → Result → Why it matters here → Connections
- **moc** — Scope → Key concepts → Raw material → Threads

## Workflow

**Ingest:** read the raw file → write one `wiki/` page with a `raw:` field → run the linter (it flips the row to `digested`) → append to `meta/log.md`.

**Triage:** anything in `raw/inbox/` gets moved to a kind folder or deleted. The inbox is a queue, not storage.

**Query:** read `index.md` first, then follow wikilinks.
