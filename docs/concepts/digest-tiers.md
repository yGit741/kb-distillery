# Digest tiers

A digest turns a cataloged source into a page. There are three tiers. Each tier costs more and reads more.

| Tier | Command | Model | Result | Rough input |
|---|---|---|---|---|
| easy | `distill digest easy <slug-or-raw>` | light (Haiku by default) | Abstract skim. Problem and Main result only. | 2k to 4k tokens |
| full | `distill digest full <raw>` | medium | Full note with key equations. | 8k to 12k tokens |
| deep | `distill digest deep <raw> --confirm-heavy` | heavy | Full note plus links to neighbouring sources, question stubs and topic threads. | 25k to 40k tokens or more |

The page records the tier in its `depth` field: `listed` (cataloged, not read), `easy`, `full` or `deep`.

## Rules

- A bare request to "digest" asks you for a tier. It never starts a full or deep digest by itself.
- A deep digest needs `--confirm-heavy`.
- About one in twenty easy digests is re-read by a stronger model (`ingest easy-spotcheck`).
- A digest reads `raw/` and writes `wiki/`. It runs inside a transactional session: `begin`, `extract`, `map`, `draft`, `finalize`. Direct writes to the session's wiki paths are blocked until it ends.
- A finished digest is one `kb(digest)` commit.

## Batches and books

- `distill digest many`: fills claims for many sources in one batch, then runs the full digest on each.
- `--chapter N`, `--chapters A-B`, `--all`, `--section SPEC`: digest a book by chapter, one part page each. Ingest builds the book page first; `ingest toc <raw>` prints its chapters.
- `--row N`: digest one row of a course or series table. Pass the collection slug as the path.

## Billing

Each digest command that calls a model takes `--backend subscription|api|batch` where it supports it, or reads `KB_LLM_BACKEND`. See [ADR 0001](../adr/0001-single-llm-gateway.md).

## Instructions

`distill digest instructions --kb <id>` prints the digest focus of a knowledge base. The files are in `digest/` of the knowledge base (`focus.md`, `types.md`). See `examples/demo/digest/`.

More: [workflows.md](../../src/kb_distillery/kits/base/defaults/docs/workflows.md)
