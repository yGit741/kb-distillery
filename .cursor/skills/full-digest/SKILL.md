---
name: full-digest
description: Standard paper note via transactional ingest (~8-12k tokens, medium tier). Use ONLY for "full-digest" or "full digest". Do NOT use for bare "digest", "easy-digest", or "deep-digest".
---

# full-digest

**LLM tier:** medium · **Budget:** ~8–12k tokens in

Replaces legacy `thesis-ingest`.

## Triggers

- `full-digest`, `full digest`, `read this paper fully`

## Do NOT

- Trigger on bare `digest` — ask tier first
- Trigger on `easy-digest` or `deep-digest`
- Write `wiki/` directly during an open session
- Mark as heavy tier

## Commands

```bash
python3 -m meta.ingest full-digest <raw>   # opens session, prints next steps
python3 -m meta.ingest begin <raw>         # same session API
python3 -m meta.ingest extract <sha>       # fill claims.json — see meta/ingest/extract_prompt.md
python3 -m meta.ingest map <sha>
python3 -m meta.ingest draft <sha>
python3 -m meta.ingest finalize <sha>      # lint --ingest-strict for digestion-status full
python3 -m meta.ingest abort <sha>
```

## Agent steps after `begin` / `full-digest`

1. Run `extract` — read `meta/.ingest/<sha>/extracted.text` (first 25 pages). If
   the raw entity has a `parsed.md` sidecar (e.g. `raw/mail/<thread>/parsed.md`),
   `extracted.text` is that sidecar's content instead of raw PDF/thread text.
2. Write `claims.json` with real LaTeX equations, results, concepts.
3. Set `person` from `raw/papers/<person>/…` when applicable.
4. Re-run `extract` to validate.
5. `map` → `draft` → review `staging/` → `finalize`.

## Output

`digestion-status: full`, `status: digested`, Key equations required at finalize.

## Quality bar

- Key equations: real LaTeX, not `—`
- Concepts link to existing wiki slugs
- MOC `## Papers` updated via finalize
- Person link when raw is under researcher folders
