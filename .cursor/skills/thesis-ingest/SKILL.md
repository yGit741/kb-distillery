---
name: thesis-ingest
description: Transactional paper ingest for the thesis wiki — begin, extract claims, map, draft, finalize. Use when ingesting a PDF from raw/papers/ into wiki/.
---

# Thesis ingest

One paper per session. Read `AGENTS.md` and `meta/ingest/extract_prompt.md`.

## Commands

```bash
python3 -m meta.ingest begin raw/papers/<path>.pdf
python3 -m meta.ingest extract <sha>   # fill claims.json first if template
python3 -m meta.ingest map <sha>
python3 -m meta.ingest draft <sha>
python3 -m meta.ingest finalize <sha>  # lint --ingest-strict
python3 -m meta.ingest abort <sha>     # on failure
```

## Agent steps after `begin`

1. Run `extract` — read `meta/.ingest/<sha>/extracted.text` or the PDF.
2. Write `claims.json` with LaTeX equations (non-empty), results, concepts.
3. Re-run `extract` to validate.
4. `map` → `draft` → review `staging/` → `finalize`.

Do **not** write `wiki/` directly while session is open — guard blocks locked paths.

## Quality bar

- Key equations: real LaTeX, not `—`
- Concepts link to existing wiki slugs (`meta/aliases.tsv` helps)
- MOC `## Papers` gets the digest via finalize
