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
```

Writes `meta/.ingest/easy/<sha>/abstract.text` for agent summary. Sets `digestion-status: easy`, `status: to-read`.

## Agent steps

1. Run CLI to extract abstract text
2. Read `abstract.text` (~2–4k tokens max)
3. Update wiki: **Problem**, **Main result** from abstract only
4. Run `pixi run lint`

## Commit

`easy-digest` opens an ops session for the page. After filling Problem / Main result, run `pixi run ops -- commit` to record it as one `kb(digest)` commit.
