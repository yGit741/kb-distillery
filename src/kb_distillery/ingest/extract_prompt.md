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

## Book parts: exercises and notes

When the template has an `exercises` field (a book part), fill it with **every** exercise of the part: `label` is its number as printed (`3.36`), `statement` is the full statement in LaTeX, copied, not summarised (hints included). Leave the list empty only when the part has no exercises. When the template has a `notes` field, summarise the part's historical notes and references there; without the field, leave them out.

## Marked formulas

A source that starts with `[transcript of pages …]` was read from the page images and checked. A formula followed by `[!](mark:…)` or `[!!](mark:…)` was not settled (`!`: probably right, `!!`: unsettled). Its crop of the original page is `meta/parsed/<raw-sha1>/crops/p<page>-<n>.png` (the link is `mark:<first 12 of the sha1>/p<page>/<n>`). For a marked formula you use: open the crop, write what it shows; drop the link when the crop settles it, keep the link right after the formula when it does not (in `equations`, put the link in the item's `mark` field, never inside `latex`). Never drop a `[!!]` link without looking at its crop.
