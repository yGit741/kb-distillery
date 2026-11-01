---
name: export-kb
description: >-
  Pack wiki + think text into a timestamped zip under .exported/ for sharing
  with external LLMs. Use for export-kb, export kb, share kb, kb zip. Do NOT commit .exported/.
---

# export-kb

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `export-kb`, `export kb`, `share kb`, `kb zip`, `export for llm`

## Do NOT

- Commit `.exported/` — gitignored
- Hand-edit the zip — re-run the CLI
- Include PDFs unless the user explicitly asks (large)

## CLI

```bash
python3 -m kb_distillery.publish.export
python3 -m kb_distillery.publish.export --list
python3 -m kb_distillery.publish.export --skip-lint          # faster; index may be stale
python3 -m kb_distillery.publish.export --include-raw-pdfs   # full raw/ binaries (large)
```

Pixi: `pixi run export-kb`

## Output

`.exported/yonatan-thesis-kb-<YYYY-MM-DDTHHMMSSZ>.zip`

Includes:

- `AGENTS.md`, `CLAUDE.md`, `index.md`, `skills/README.md`
- `src/kb_distillery/kits/base/defaults/docs/*.md` (the docs the AGENTS.md doc router points to)
- `wiki/*.md`, `think/*.md`
- `meta/corpus.tsv`, `meta/log.md`, `meta/coherence-warnings.tsv` (if present)
- `EXPORT_MANIFEST.txt` — file list + counts

PDFs omitted by default; paths remain in `meta/corpus.tsv`.

## Agent workflow

1. Run `python3 -m kb_distillery.publish.export` (lint runs first by default).
2. Print the absolute path and size for upload to the other LLM.
3. Tell the recipient: start with `AGENTS.md` (its doc router names the `src/kb_distillery/kits/base/defaults/docs/` file to read) and `index.md`.
