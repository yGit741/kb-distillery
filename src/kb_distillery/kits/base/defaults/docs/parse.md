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

## The store

`<store>/<raw-sha1>/` is `<kb>/meta/parsed/<raw-sha1>/` in a knowledge base:

- `pNNNN.json`: `status` (`verified` without marks, `marked` with), `markdown` (mark links inline) and `marks`: each with `id`, `level`, `reason`, `text` (the formula now), `was` (what a fix replaced), `other` (the parser's reading), `box` and `crop`.
- `crops/pNNNN-<id>.png`: the block of the page the mark sits in.
- `manifest.json`: pages per status and pages still missing.

`store.transcript(root, sha, pages)` returns the joined Markdown of a page range; `store.marks(…)` the mark records.

## Commands

```
distill parse transcribe <pdf> --pages 1-5,8 --store DIR [--backend subscription|api|batch] [--max-usd N] [--dry-run]
distill parse marks --store DIR --sha <raw-sha1> [--pages …]
distill parse run|status|check|sample …        # the parser alone and the older text-layer verifier
```

A book is transcribed by chapter, several chapters, or whole, from its Chapters table (`collections.md`):

```
distill parse transcribe raw/printed-docs/<book>.pdf --kb . --chapter 3        # also 1-3, 2,appA, all
distill ingest toc raw/printed-docs/<book>.pdf                                 # per chapter: pages stored, marks
distill ingest full-digest raw/printed-docs/<book>.pdf --chapter 3 [--no-exercises] [--notes]
```

Pages already stored are not read again, so a chapter done today costs nothing when the whole book is run later. Front and back matter rows (`skip`) are never transcribed by `--chapter all`.

`transcribe` prints its cost estimate before it runs and stops when the estimate is above `--max-usd`. Everything is cached per page under `~/.cache/kb-distillery/parse/<sha12>/` (`$KB_PARSE_WORK`), so a stopped run resumes and a second run costs nothing. `--audit-model none` skips the auditor; `--engine none` skips the parser (every page then carries a page mark).

**Billing.** The reader, the judge and the auditor are `kb_distillery.llm` requests with images: the backend is the usual `--backend` / `$KB_LLM_BACKEND` choice, all three work. MinerU is local and free.

## Digest reads the transcript

With the `parsed-pdf` flag on, `ingest.extract.extract_text` returns the stored transcript of a PDF whenever every page asked for is in `meta/parsed/` (the text then starts with `[transcript of pages A-B …]`); otherwise it reads the text layer as before. A book part is stricter: `extract` refuses to run without its transcript and prints the `distill parse transcribe` command to run first.

- `extract --fill` sends the crops of the marked formulas with the request (`!!` first, at most 20) and tells the model to check each marked formula it uses against its crop: settled, the link is dropped; not settled, the link stays right after the formula. In `claims.json` an equation carries its link in `equations[].mark`; `draft` writes it after the equation.
- A book chapter's template has `exercises` (every exercise, in full; on unless the digest was started with `--no-exercises`) and, with `--notes`, `notes`. `draft` writes them as `## Exercises` and `## Notes and references` near the end of the page.
- An agent filling `claims.json` by hand follows the same rules: `extract_prompt.md`, "Marked formulas".

## Measuring

Do not trust a change to a prompt or to `compare.py` without numbers: plant known errors in stored transcripts and count how many the auditor finds, and audit unmarked formulas on pages the tuning never saw. The first measurement (38 dense pages, 114 planted errors of ten kinds) had the auditor find all 114.
