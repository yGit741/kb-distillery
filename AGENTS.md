# Thesis Wiki — agent schema

Personal knowledge base for an MSc in theoretical ML. **The thesis topic is not yet chosen** — the vault exists to explore candidate directions and decide. Follows the [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern.

## Layers

| Layer | Path | Rule |
|-------|------|------|
| **Raw** | `raw/` | User-owned inputs. **Immutable — never write here.** |
| **Wiki** | `wiki/` | Agent-owned synthesis. Flat. Create, update, cross-link. |
| **Think** | `think/` | Human-owned slow space. Schema-free. Agents never write here. |
| **Meta** | `meta/` | Schema, templates, log. |

```
raw/inbox/            reMarkable sync target. Any shape. MUST drain to zero.
raw/papers/<course>/  academic PDFs
raw/slides/<course>/  lecture decks, presentations
raw/notes/<course>/   handwritten notes, recaps, scratch
raw/web/  raw/assets/ clips, images (flat)
wiki/                 flat agent-owned notes
think/                human slow space (not linted)
_quarantine/          staged for deletion, gitignored, not part of the vault
```

## meta/lint.py IS the schema

Prose rules drift; this doesn't. If `python3 meta/lint.py` passes, the write is legal.

**Environment:** one-time `curl -fsSL https://pixi.sh/install.sh | bash`, then restart the shell. All tasks below work via `pixi run <task>`.

```
pixi run lint                      check + reconcile + regenerate index.md
pixi run health                    terminal health summary
pixi run dashboard                 localhost health UI (http://127.0.0.1:8765)
pixi run lint-strict               ingest-finalize checks
pixi run ingest-status             open ingest sessions
pixi run distill-propose -- <slug> propose graph brief from think page
pixi run distill-apply -- <slug>   apply distill plan to public KB
pixi run sync-skills               copy meta/skills/ → .cursor/skills/
```

Without pixi, use `python3` equivalents (`python3 meta/lint.py`, `python3 -m meta.dashboard`, …).

**Write guardrails:** `meta/guard.py` blocks illegal agent writes via preToolUse hooks in both `.cursor/hooks.json` (Cursor) and `.claude/settings.json` (Claude Code). Keep both pointed at the same script. `CLAUDE.md` imports this file for Claude instruction parity.

**Commit gate:** `.git/hooks/pre-commit` runs `meta/lint.py`. Do not hand-edit `index.md` or `meta/corpus.tsv` — both are generated on every lint run. `python3 meta/lint.py --health` or `python3 -m meta.dashboard` for vault health.

## Frontmatter

```yaml
type: concept | question | person | paper | source | moc | distilled-think
status: seed|growing|solid   (question: open|partial|resolved; paper: to-read|reading|digested; distilled-think: review|applied|archived)
digestion-status: catalog|easy|full|deep   # papers only — depth of write-up
area: [info-theory]          # papers: theme slugs only (whitelist in meta/schema.py THEME_SLUGS)
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
- **moc** — Scope → Key concepts → Raw material → Threads (research themes only)
- **distilled-think** — Summary (review prose) → Proposed propagation → Not promoting (transient; use `--cleanup` after apply)
- **source** — Scope → Key concepts → Raw material → Threads (course provenance)

## Theme whitelist (paper `area:`)

`statistics`, `optimization-theory`, `learning-theory`, `info-theory`, `implicit-regularization`, `tensor-factorization`, `complex-nn`, `quantum`. Course slugs use `source-*` pages, not MOCs.

## Semantic lint

**Structural lint** (`meta/lint.py`): links, schema, inbox — unchanged.

**Semantic lint** (`meta/coherence.py`): meaning-level checks, 0 LLM.

| kind | meaning | action |
|------|---------|--------|
| `internal` | bad ingestion — wiki stale/wrong vs source | **fix** (re-digest / edit); score ≥ 70 → lint ERROR |
| `external` | two digested papers disagree | **note** on each paper's `## Connections` / `## Links out` |
| `cosmetic` | graph hygiene | warn only |

```
python3 meta/coherence.py status
python3 meta/coherence.py fixed <id>    # internal resolved
python3 meta/coherence.py noted <id>    # external recorded on paper
python3 meta/coherence.py dismiss <id>
python3 meta/semfind.py moc moc-info-theory
```

Manifest: `meta/coherence-warnings.tsv` (regenerated on lint; statuses persist).

After full/deep digest or distill apply: `SEMFIND_READY` → `meta/skills/semantic-lint-hop/SKILL.md`. On-demand theme pass: `meta/skills/lint-moc/SKILL.md`.

## Distill think

Human writes in `think/*.md` (schema-free). Distill produces a transient `wiki/distilled-think-*.md` for review, then patches the public KB on apply.

```
python3 -m meta.distill propose <think-file>              # → distilled-think page + plan.json
python3 -m meta.distill revise <think-file>               # re-read think/, keep edited Summary
python3 -m meta.distill apply <think-file> --cleanup       # propagate + delete distilled page
python3 -m meta.distill abort <think-file>
```

`think/` is never agent-edited. See `meta/skills/distill-think/SKILL.md`.

## Skill ladder

Read `meta/skills/README.md` before any workflow. Run `pixi run sync-skills` after editing skills.

| Skill | LLM tier | Budget (in) | Trigger |
|-------|----------|-------------|---------|
| `scrap-data` | none | 0 | scrap, download, save to inbox |
| `ingest-to-catalog` | none | 0 | catalog, triage inbox, drain inbox |
| `easy-digest` | light | ~2–4k | `easy-digest`, `easy digest`, `skim` |
| `full-digest` | medium | ~8–12k | `full-digest`, `full digest` only |
| `deep-digest` | heavy | ~25–40k+ | `deep-digest` + user confirms heavy |
| `distill-think` | medium | ~8–12k propose | `distill-think`, `distill think`, `graph brief` |
| `query-kb` | light–medium | ~3–15k | `query-kb`, `query kb`, `what do I know about` |
| `semantic-lint-hop` | light–medium | ~3–12k | after full/deep digest finalize or distill apply |
| `lint-moc` | medium | ~8–20k | `lint-moc`, `lint moc` |

**`digest` alone → ask tier (easy / full / deep).** Bare "digest" never triggers `full-digest`.

**Dedup:** always `resolve` before `scrap`. If FOUND → cite `[[slug]]`; don't re-download.

```
python3 -m meta.ingest resolve <url|arxiv|slug> # check vault first (0 LLM)
python3 -m meta.ingest scrap <url>              # → raw/inbox/ (blocked if duplicate)
python3 -m meta.ingest catalog <inbox-path>     # → raw/papers/ + wiki stub
python3 -m meta.ingest easy-digest <slug|raw>   # light abstract skim
python3 -m meta.ingest full-digest <raw>        # medium: begin→finalize
python3 -m meta.ingest deep-digest <raw> --confirm-heavy
```

During `full-digest` / `deep-digest`, `meta/guard.py` blocks direct writes to session-owned wiki paths — use `draft` + `finalize`. Legacy `reingest-*` is bootstrap-only.

**Triage:** anything in `raw/inbox/` gets cataloged or deleted. The inbox is a queue, not storage.

**Query:** Karpathy Query operation — read wiki, cite `[[slugs]]`, file good answers back on request. See `meta/skills/query-kb/SKILL.md`.

```
python3 meta/query.py candidates "<keywords>"   # rank slugs (0 LLM)
python3 meta/query.py mocs                      # theme entry points
```

Workflow: `index.md` → `candidates` → read 3–8 pages → synthesize. Not the same as `meta.ingest resolve` (ingest dedup).
