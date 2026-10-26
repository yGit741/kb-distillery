---
name: easy-digest
description: Lightweight abstract/metadata skim of a Source page to depth easy (~2-4k tokens, Haiku by default). Use ONLY for "easy-digest", "easy digest", or "skim". Do NOT use for bare "digest" (ask tier first) or "full-digest".
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
python3 -m kb.ingest easy-digest <slug|raw>
python3 -m kb.ingest easy-digest <raw> --into <series page>     # numbered parts share one page
python3 -m kb.ingest easy-digest <raw> --no-tick --no-lint --no-commit   # batch: orchestrator ticks, lints, commits
```

**Series:** when posts are explicit parts of one thing (week 1…7, part I…III), create the page once, then
`--into` adds each clip to its `raw:` list and ticks that row with the same page. **Batch:** with `--no-tick
--no-lint --no-commit` the command only writes the page; the orchestrator opens one ops session for the
batch, ticks rows (`course.record_row`), lints once and commits once (`kb(digest)`). `KB_CI=1` lets this
run in a clone without the raw binaries: their manifest rows are kept as they are.

Writes `meta/.ingest/easy/<sha>/abstract.text` for agent summary. A video bundle (`raw/videos/<name>/video.md`,
from `scrap-youtube`) is skimmed from its metadata, description, chapters, frame text and the start and end of the
transcript; the new `video-<name>` page gets its title, url and channel from the bundle. Deepens the Source page in place
(a `depth: listed` catalog stub becomes `depth: easy`, `status: digested` — lint requires `digested`
for any easy/full/deep depth). If the raw file is a course/series member, its `## Contents` row is
ticked `easy`.

## Model

Easy digests run on **Haiku** by default — the cheapest model (e.g. a Task/agent with model
`haiku`); the summary is a skim of the abstract, not analysis.

**Spot-check (~5%).** A deterministic pick chooses which easy digests a stronger model (Sonnet)
re-reads against the raw file; it logs a verdict per page to `meta/.ingest/easy/spotcheck.jsonl`:

```bash
python3 -m kb.ingest easy-spotcheck pick <slug...>      # which of these slugs to re-read
python3 -m kb.ingest easy-spotcheck log <slug> --model <m> --verdict ok|fix [--note "..."]
```

A `fix` verdict means the page is corrected (in an ops session, see `wiki-edit`) or re-digested.

## Agent steps

1. Run CLI to extract abstract text
2. Read `abstract.text` (~2–4k tokens max)
3. Update wiki: **Problem**, **Main result** from abstract only
   (a `q-` page you touch: keep its H1 a short name ≤ 80 chars and fill `## Question` with the formal statement)
4. Run `pixi run lint`
5. For a batch: `easy-spotcheck pick` over the new slugs; have Sonnet re-read the picked ones and
   `easy-spotcheck log` each verdict

## Commit

`easy-digest` opens an ops session for the page. After filling Problem / Main result, run `pixi run ops -- commit` to record it as one `kb(digest)` commit.
