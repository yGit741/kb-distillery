# Extract claims — agent prompt

Read `meta/.ingest/<sha>/extracted.text` (or the PDF at `session.raw`).

Write `claims.json` in the same session directory. **All math in LaTeX** (`$…$` inline, `$$…$$` block). Do not prose-summarize proofs — extract defining equations into `equations[]` with `variables`.

Required fields:
- `raw`, `title`, `problem`, `method`, `results` (array, non-empty)
- `equations` (array, non-empty; each item: `latex`, `variables`, `label`)
- `concepts` (bare slugs or phrases — `map` resolves via aliases.tsv)
- `open_questions` (optional; spawn q- pages if novel)
- `year`, `authors`, `citekey`, `url` when known
- `person` — bare slug from `raw/papers/<person>/…` (required for researcher bibliographies)

Validate: `python3 -m kb.ingest extract <sha>`
