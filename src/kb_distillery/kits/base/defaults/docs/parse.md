# PDF transcripts: reader, parser, judge, auditor and marks

> How the pages of a PDF become a checked Markdown transcript with `!` / `!!` marks. Part of the doc router in [`AGENTS.md`](../../../../../../AGENTS.md). Dark behind the `parsed-pdf` flag; code in `src/kb_distillery/parse/`.

## Why

The text layer of a typeset PDF loses mathematics: symbols drop out, scripts land on their own line, nothing is LaTeX. A transcript is made from the page image instead, by several readers that check each other, and every place where a single voice decided carries a mark so a later reader knows where to look at the original.

## The chain

| Step | Module | What it does | Cost |
|---|---|---|---|
| parser | `engines/mineru.py`, `run.py` | MinerU, local, per page: Markdown plus the box of every block | none, about a minute a page |
| reader | `reader.py` | a vision model transcribes the page image (it never sees the parser's output) | one model call a page |
| compare | `compare.py` | both pages become streams of canonical tokens (LaTeX style, spacing and the prose/maths border do not matter) and are aligned | none |
| judge | `judge.py` | for each place the two differ, a model looks at the page again with both readings | one call a page that has differences |
| auditor | `audit.py` | a stronger model reads the finished page against the image and lists every difference | one call a page |
| figures | `figures.py` | each figure the reader placed (`![](figure)`) is paired with the parser's image region, cut as a PNG, linked, and described by a model | one call a figure |
| store | `transcribe.py`, `store.py` | fixes applied, marks placed, crops cut, page written | none |

The reader's page is the transcript; the parser is the independent witness and gives the geometry for the crops. Running heads and page numbers are left out by both.

## Marks

A mark is a Markdown link right after the formula it belongs to: `[!](mark:<sha12>/p0188/3)` or `[!!](…)`.

| Case | Mark |
|---|---|
| parser and reader agree, the auditor finds nothing | none |
| they differ, the judge is sure the transcript is right | none |
| the judge is sure it is wrong and gives a fix | fix applied, `!` |
| the judge hesitates or does not answer | `!!` |
| the reader wrote `\unsure{…}` | `!` |
| the auditor finds a difference and is sure of its fix | fix applied, `!` |
| the auditor is unsure, gives no fix, or its place cannot be found | `!!` |
| only the reader produced the page | one mark for the whole page, `!` |
| only the parser produced the page | the auditor checks the parser's page; one mark for the whole page: `!` when it did, `!!` when it did not (the auditor is off, the cost ceiling skipped it, or its answer was unreadable twice) |

`!` means "one voice decided, probably right". `!!` means "nobody could settle it": whoever uses the formula must look at the crop.

A reader reply can come back cut or refused: models stop long verbatim copies of prose-heavy book pages (a chapter's opening page, a preface). The reply must hold the page between `<<<PAGE` and `PAGE>>>` lines, so a cut reply is never mistaken for a page; it is tried once more, then the parser's page stands in.

## Figures

The reader writes a figure as `![](figure)` followed by its caption, and never transcribes what is drawn inside it. The parser's image regions (glyph-sized ones dropped) are paired with those placeholders in reading order. Each figure becomes `![Figure 3.1](figure:<sha12>/p0073/1)` in the page, a PNG `figures/p0073-1.png` and a record in the page's `figures` list: `id`, `label` ("Figure 3.1", from the caption), `caption`, `box`, `file`, `description` and `problem`.

- **Description.** One `kb_distillery.llm` request per figure, sent with its crop and caption. The model describes what is drawn (kind of figure, axes, curves, nodes, labels in LaTeX) between `<<<FIGURE` and `FIGURE>>>` lines, and a reply without those lines is tried once more. It is cached per crop under the work dir, so an unchanged figure is never asked twice. `--no-figure-descriptions` skips it.
- **Problems.** A placeholder with no region keeps the whole page as its crop. A region the reader did not place is added at the end of the page. Both get a `!!` mark right after the figure link.
- **Explorer.** `GET /api/figures/<sha12>/p0073/1` serves the PNG, and the page renderer draws a `figure:` image from it.
- **Digest.** A digest of transcribed pages lists every figure under `## Figures`: the image, its caption and its description. `extract` writes them to `figures.json` in the session and `draft` writes the section, so a figure never depends on the model remembering it. The text the model reads has each description after its figure.

## Completeness

`distill parse complete <pdf> --pages … --store DIR` counts what reached the transcript against independent witnesses. It calls no model and exits 1 when something needs a look.

- **Formulas.** Every display formula the parser read is lined up with the transcript; one of which less than half is found is listed as possibly missing. The share of the parser's maths tokens found is the page's coverage. A split or merged display formula can show up as a false alarm, so open the page before trusting the report.
- **Figures.** The number of parser regions, the number of figure links, and the captions the PDF's text layer prints ("Figure 3.1") must agree; every figure with a `problem` is listed.

The five test chapters (105 pages, 3 books): 284 of 285 display formulas were found (the one miss is a formula the two readings split differently), 98 to 99.8% maths coverage, and 11 of 11 figures were cut, captioned and described.

## The store

`<store>/<raw-sha1>/` is `<kb>/meta/parsed/<raw-sha1>/` in a knowledge base:

- `pNNNN.json`: `status` (`verified` without marks, `marked` with), `markdown` (mark links inline) and `marks`: each with `id`, `level`, `reason`, `text` (the formula now), `was` (what a fix replaced), `other` (the parser's reading), `box` and `crop`.
- `crops/pNNNN-<id>.png`: the block of the page the mark sits in.
- `figures/pNNNN-<id>.png`: each figure, cut from a 2400-pixel render of the page.
- `manifest.json`: pages per status and pages still missing.

`store.transcript(root, sha, pages)` returns the joined Markdown of a page range; `store.marks(…)` the mark records.

## Commands

```
distill parse transcribe <pdf> --pages 1-5,8 --store DIR [--backend subscription|api|batch] [--max-usd N] [--dry-run]
distill parse marks --store DIR --sha <raw-sha1> [--pages …]
distill parse complete <pdf> --pages … --store DIR [--json]   # formulas and figures found, no model call
distill parse run|status|check|sample …        # the parser alone and the older text-layer verifier
```

`transcribe` prints its cost estimate before it runs and stops when the estimate is above `--max-usd`. Everything is cached per page under `~/.cache/kb-distillery/parse/<sha12>/` (`$KB_PARSE_WORK`), so a stopped run resumes and a second run costs nothing. `--audit-model none` skips the auditor; `--engine none` skips the parser (every page then carries a page mark).

**Billing.** The reader, the judge, the auditor and the figure descriptions are `kb_distillery.llm` requests with images: the backend is the usual `--backend` / `$KB_LLM_BACKEND` choice, all three work. MinerU is local and free.

## Digest reads the transcript

With the `parsed-pdf` flag on, `ingest.extract.extract_text` returns the stored transcript of a PDF whenever every page asked for is in `meta/parsed/` (the text then starts with `[transcript of pages A-B …]`); otherwise it reads the text layer as before. A book part is stricter: `extract` refuses to run without its transcript and prints the `distill parse transcribe` command to run first.

- `extract --fill` sends the crops of the marked formulas with the request (`!!` first, at most 20) and tells the model to check each marked formula it uses against its crop: settled, the link is dropped; not settled, the link stays right after the formula. In `claims.json` an equation carries its link in `equations[].mark`; `draft` writes it after the equation.
- A book part's template has `exercises` (every exercise, in full; on unless the session's scope says `exercises: false`) and, on request (`notes: true`), `notes`. `draft` writes them as `## Exercises` and `## Notes and references` near the end of the page.
- An agent filling `claims.json` by hand follows the same rules: `extract_prompt.md`, "Marked formulas".

## Measuring

Do not trust a change to a prompt or to `compare.py` without numbers: plant known errors in stored transcripts and count how many the auditor finds, and audit unmarked formulas on pages the tuning never saw. The first measurement (38 dense pages, 114 planted errors of ten kinds) had the auditor find all 114.
