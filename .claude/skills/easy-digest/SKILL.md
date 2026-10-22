---
name: easy-digest
description: Lightweight abstract/metadata skim (~2-4k tokens). Use ONLY for "easy-digest", "easy digest", or "skim". Do NOT use for bare "digest" (ask tier first) or "full-digest".
---

# easy-digest

**LLM tier:** light · **Budget:** ~2–4k tokens in

## Triggers

- `easy-digest`, `easy digest`, `skim`

## Do NOT

- Trigger on bare `digest` — ask easy / full / deep first
- Trigger on `full-digest` or `full digest`
- Read more than ~3 PDF pages
- Require Key equations

## CLI

```bash
python3 -m meta.ingest easy-digest <slug|raw>
python3 -m meta.ingest easy-digest <raw> --into <series page>     # numbered parts share one page
python3 -m meta.ingest easy-digest <raw> --no-tick --no-lint --no-commit   # batch: orchestrator ticks, lints, commits
```

**Series:** when posts are explicit parts of one thing (week 1…7, part I…III), create the page once, then
`--into` adds each clip to its `raw:` list and ticks that row with the same page. **Batch:** with `--no-tick
--no-lint --no-commit` the command only writes the page; the orchestrator opens one ops session for the
batch, ticks rows (`course.record_row`), lints once and commits once (`kb(digest)`). `KB_CI=1` lets this
run in a clone without the raw binaries: their manifest rows are kept as they are.

Writes `meta/.ingest/easy/<sha>/abstract.text` for agent summary. Sets `digestion-status: easy`, `status: digested` (lint requires `digested` for any easy/full/deep
tier). If the raw file is a course/series member, its `## Contents` row is ticked `easy`.

## Agent steps

1. Run CLI to extract abstract text
2. Read `abstract.text` (~2–4k tokens max)
3. Update wiki: **Problem**, **Main result** from abstract only
4. Run `pixi run lint`

## Commit

`easy-digest` opens an ops session for the page. After filling Problem / Main result, run `pixi run ops -- commit` to record it as one `kb(digest)` commit.
