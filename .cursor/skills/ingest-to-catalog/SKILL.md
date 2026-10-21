---
name: ingest-to-catalog
description: Move inbox files to raw/ format folders, record collection membership, and create lean paper stubs. Zero LLM. Use for "catalog", "triage inbox", "ingest to catalog". Do NOT read PDFs or digest.
---

# ingest-to-catalog

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `catalog`, `triage inbox`, `ingest to catalog`, `drain inbox`

## Do NOT

- Read PDF body text
- Run any digest tier
- Write wiki prose beyond the stub template
- Move a raw file after catalog — reclassifying = editing its corpus `collection` cell

## CLI

```bash
python3 -m meta.ingest catalog <inbox-path> [--collection <hub|person>] [--format <folder>] [--title T]
python3 -m meta.ingest drain-inbox [--collection <hub|person>] [--match <name prefix>]
```

`--course` is an alias of `--collection`. `--format` overrides detection (e.g. `presentations`
for a slide-deck PDF). `--title` names the row added to a course/series `## Contents` table.

## Subskills

| Subskill | Role |
|----------|------|
| [detect](detect/SKILL.md) | Inspect file → format folder |
| [articles](articles/SKILL.md) | typed PDF → `raw/printed-docs/` (+ `paper-` stub if not a course/series member) |
| [mail](mail/SKILL.md) | thread bundle → `raw/emails/<YYYY-MM-DD-thread>/` (corpus row only) |
| [chat](chat/SKILL.md) | Gemini-style `.md` export → `raw/llm-chats/` (corpus row only) |
| [notes](notes/SKILL.md) | ink-only PDF → `raw/handwritten/` (corpus row only) |
| [slides](slides/SKILL.md) | deck → `raw/presentations/` (corpus row only) |
| [web](web/SKILL.md) | clip → `raw/web-clips/` (corpus row only) |
| [blog](blog/SKILL.md) | blog post → `raw/web-clips/` or `raw/printed-docs/` (corpus row only) |

## Output

- Every format: the file lands flat in `raw/<format>/` and gets a `meta/corpus.tsv` row.
- `--collection <course-|series->`: corpus `collection` set **and** a `—` row appended to the
  hub's `## Contents` table. Other members are renamed `<short>-<topic>.<ext>` (hub `short:`).
- `--collection <book-|person>`: corpus `collection` cell only (person = researcher bibliography).
- An image named `<clip stem>-NN.<ext>` whose clip is in the inbox or `raw/web-clips/` is that clip's figure:
  it goes to `raw/images/` with no collection and lint binds it as `asset:<clip>` (never backlog, never a hub row).
  `drain-inbox` catalogs clips before figures and lints once at the end.
- A paper gets a `wiki/paper-<year>-<title>.md` stub and a tagged blog post a `blog-…` page, both
  `digestion-status: catalog`, `status: to-read`. Emails, chats, handwriting and slides stay corpus
  rows until digested. Every outcome (success or refusal + reason) is logged in `meta/.catalog/`.

Lint runs at the end of each catalog.

## Commit

The CLI commits this operation itself as `kb(catalog): … (kb-x.y.z)` on main — only the files it changed (`--no-commit` to skip). Check with `pixi run ops -- log -n 1`. `drain-inbox` makes one commit for the whole drain.
