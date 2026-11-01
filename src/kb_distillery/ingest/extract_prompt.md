# Extract claims — agent prompt

Read `meta/.ingest/<sha>/extracted.text` (or the PDF at `session.raw`).

Write `claims.json` in the same session directory. **All math in LaTeX** (`$…$` inline, `$$…$$` block). Do not prose-summarize proofs — extract defining equations into `equations[]` with `variables`.

Required fields:
- `raw`, `title`, `problem`, `method`, `results` (array, non-empty)
- `equations` (array, non-empty; each item: `latex`, `variables`, `label`)
- `concepts` (bare slugs or phrases — `map` resolves via aliases.tsv)
- `open_questions` (optional; spawn q- pages if novel — each a short question, ≤ 80 chars: the stub's H1 is its name, the sentence lands in `## Question`)
- `year`, `authors`, `citekey`, `url` when known
- `person` — bare slug from `raw/papers/<person>/…` (required for researcher bibliographies)

Validate: `python3 -m kb_distillery.ingest extract <sha>`
