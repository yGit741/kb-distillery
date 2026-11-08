# Workflows and the ingest CLI

> Skill ladder, dedup, ingest/digest commands, scrap-wordpress, scrap-youtube, arXiv rules, catalog, query, distill. Part of the doc router in [`AGENTS.md`](../../../../../../AGENTS.md).

## Skill ladder

Skills live in `src/kb_distillery/kits/<kit>/skills/` (what a kb is given, as `.claude/skills/` in the kb) and `.claude/skills/` (the engine's own). Run `pixi run lint-skills` after editing skills; `docs/guides/write-a-skill.md` says how to write one.

| Skill | LLM tier | Budget (in) | Trigger |
|-------|----------|-------------|---------|
| `scrap-data` | none | 0 | scrap, download, save to inbox, pull from google drive |
| `ingest-to-catalog` | none | 0 | catalog, triage inbox, drain inbox |
| `easy-digest` | light (Haiku; ~5% Sonnet spot-check) | ~2–4k | `easy-digest`, `easy digest`, `skim` |
| `full-digest` | medium | ~8–12k | `full-digest`, `full digest` only |
| `deep-digest` | heavy | ~25–40k+ | `deep-digest` + user confirms heavy |
| `distill-think` | medium | ~8–12k propose | `distill-think`, `distill think`, `graph brief` |
| `export-kb` | none | 0 | `export-kb`, `export kb`, `share kb` |
| `query-knowledge` | light–medium | ~3–15k | `query-knowledge`, `query-kb`, `query kb`, `what do I know about` |
| `explore-raw-data` | light | ~2–6k | `explore-raw-data`, `explore raw`, `which sources do I have on …`, `is this paper worth digesting` |
| `semantic-lint-hop` | light–medium | ~3–12k | after full/deep digest finalize or distill apply |
| `lint-moc` | medium | ~8–20k | `lint-moc`, `lint moc`, `lint topic` (topic audit) |
| `build-researcher-profile` | light | ~3–8k verify | `build researcher profile`, `index researcher` |
| `share-kb` | none | 0 | share/publish the site, deploy main, deploy status, rollback, snapshot the site, list/remove snapshots, audit (not `export-kb`) |
| `create-skill` | none | 0 | create skill, new skill (meta; not in digest ladder) |

```
python3 -m kb_distillery.ingest resolve <url|arxiv|slug> # check vault first (0 LLM)
python3 -m kb_distillery.ingest scrap <url>              # → raw/inbox/ (blocked if duplicate)
python3 -m kb_distillery.ingest scrap-mail <mbox-or-eml> # → raw/inbox/mail-.../ (thread + attachments)
python3 -m kb_distillery.ingest scrap-gdrive --dry-run   # preview a mounted Drive folder pull (0 bytes)
python3 -m kb_distillery.ingest scrap-wordpress <site> --prefix <collection short>   # every post of a WordPress.com blog + figures → inbox
python3 -m kb_distillery.ingest scrap-youtube <url>   # a lecture/video → inbox video-<name>/ bundle: transcript + anchors (0 LLM)
python3 -m kb_distillery.ingest video-digest raw/videos/<name>/video.md --tier full|deep   # read the top anchors with Claude
python3 -m kb_distillery.ingest catalog <inbox-path>     # → raw/<format>/ (+ paper- Source page at depth listed, papers only)
python3 -m kb_distillery.ingest catalog <inbox-path> --collection <collection|person> [--format <folder>] [--title T]
python3 -m kb_distillery.ingest easy-digest <slug|raw>   # depth easy: abstract skim (ticks a collection row if a member)
python3 -m kb_distillery.ingest easy-digest <raw> --into <page> [--no-tick --no-lint]   # series page / batch mode
python3 -m kb_distillery.ingest full-digest <raw>        # medium: begin→finalize
python3 -m kb_distillery.ingest full-digest <collection-slug> --row N   # one course/series Contents row
python3 -m kb_distillery.ingest easy-spotcheck pick <slug...>      # ~5% of easy digests for a Sonnet re-read
python3 -m kb_distillery.ingest easy-spotcheck log <slug> --model <m> --verdict ok|fix [--note ...]
python3 -m kb_distillery.ingest deep-digest <raw> --confirm-heavy
python3 -m kb_distillery.ingest toc <raw>                # book partition (or a proposed one) (0 LLM)
python3 -m kb_distillery.ingest refetch-raw [--apply]    # replace paper PDFs stamped with another arXiv id than their page cites (0 LLM)
```

**scrap-wordpress** pulls a whole WordPress.com blog through its public API (0 LLM): one Markdown clip per
post with every formula restored losslessly from the LaTeX image URLs, embedded players as links, and the
figures downloaded next to it as `<clip stem>-NN.<ext>` (original URL kept as the link title; a figure that
cannot be fetched stays a remote link). `--since`/`--limit` resume or trial a pull; dedup is by post URL.
Then `drain-inbox --collection <series-slug>`: clips become `raw/web-clips/` members of the series, their
figures `raw/images/` rows bound as `asset:<clip>` (lint derives this from the names), one lint at the end.

**arXiv is never guessed.** The metadata client (`src/kb_distillery/ingest/arxiv_meta.py`) spaces calls 3 s apart
and retries 429/5xx; when it still cannot answer, `catalog` refuses the file (it stays in the inbox
with the reason in `meta/.catalog/failures.jsonl`) instead of filing it as `2000-untitled.pdf`, and
`backfill-authors --fix-urls` leaves the url untouched instead of clearing it. The researcher
pipeline fetches the record behind Semantic Scholar's arXiv id and downloads only when it is this
paper (a known author or most of the title), else searches by title, else skips; the downloaded PDF's
page-1 stamp must equal the id. Lint warns when a paper page's PDF is stamped with a different id
than its `url:` (a wrong download; stamps are cached in `.cache/arxiv-stamps.json`), and
`refetch-raw --apply` replaces such PDFs — the sha1 change re-queues the row, and the page must be
re-digested because its digest is of the other paper.

**Catalog** routes an inbox file to its format folder (`--format` overrides detection, e.g.
`presentations` for a slide-deck PDF) and writes the corpus row. `--collection` (alias `--course`)
fills the `collection` cell; a course/series collection also appends a Contents row (`--title`).
Catalog creates the Source page at `depth: listed` for papers (`paper-`) and tagged blog posts
(`blog-`) — emails, chats, handwriting and slides stay corpus rows until something is digested from them. Every outcome,
including a refusal and its reason, is logged in `meta/.catalog/` (the dashboard's Ingestion status).

During `full-digest` / `deep-digest`, `src/kb_distillery/git/guard.py` blocks direct writes to session-owned wiki paths — use `draft` + `finalize`.

**Triage:** anything in `raw/inbox/` gets cataloged or deleted. The inbox is a queue, not storage.

**Query:** Karpathy Query operation — read wiki, cite `[Title](slug.md)` links, file good answers back on request. See `.claude/skills/query-knowledge/SKILL.md`. Raw sources are reached only through `explore-raw-data` (`python3 -m kb_distillery.search.explore_raw find|read|check|recommend`, cataloged files only, 0 LLM): `.claude/skills/explore-raw-data/SKILL.md`.

```
python3 -m kb_distillery.search.query candidates "<keywords>"   # rank slugs (0 LLM)
python3 -m kb_distillery.search.query mocs                      # topic pages (theme-*) as entry points
```

**Full text:** `distill search text "<query>"` (also `GET /api/search/text`, the second tier of the graph search line) searches pages, think notes, chats (`.local/sessions/`) and raw `.md`/`.txt` text through one SQLite FTS5 index at `<kb>/.cache/search/fts.sqlite`. It is local and never committed (`.cache/` is gitignored), is built on the first search, is refreshed from a cheap stat scan (document count and newest mtime) and is updated after every knowledge step, think-note save and chat save (`kb_distillery.search.fts`); `--rebuild` starts over.

Workflow: `wiki/index.md` (root) → the one `wiki/<type>/index.md` section you need → `candidates` → read 3–8 pages → synthesize. Not the same as `kb_distillery.ingest resolve` (ingest dedup).

## Distill think

Human writes in `think/*.md` (schema-free). Distill produces a transient `wiki/distilled-think-*.md` for review, then patches the public KB on apply.

```
python3 -m kb_distillery.distill propose <think-file>              # → distilled-think page + plan.json
python3 -m kb_distillery.distill revise <think-file>               # re-read think/, keep edited Summary
python3 -m kb_distillery.distill apply <think-file> --cleanup       # propagate + delete distilled page
python3 -m kb_distillery.distill abort <think-file>
```

`think/` is never agent-edited. See `.claude/skills/distill-think/SKILL.md`.

## Providers

Every LLM call goes through `kb_distillery.llm`, which has two independent choices. The **backend** is how a call is billed
and run: `subscription` (`claude -p`), `api` or `batch` (`--backend`, `$KB_LLM_BACKEND`). The **provider** is the model
vendor: `claude` (default), `openai` or `gemini` (`--provider`, `$KB_LLM_PROVIDER`, or `Request.provider`). Each non-Claude
provider is a small stdlib adapter in `llm/providers/`; it runs on the `api` backend only (subscription and batch are
Claude-only and raise `LLMError`) and takes text, not images. Keys come from `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or
`GEMINI_API_KEY`, or the file `~/.config/kb-distillery/<provider>_key`; `llm.availability()["providers"]` reports which
are usable. A request's model must belong to its provider (`gpt-4.1-mini`, `gemini-2.5-flash`, or a Claude alias).
Example: `pixi run llm -- ask "hello" --provider openai --model gpt-4.1-mini`.

### Model tiers

Features ask for a tier, not a model: `light` (quick answers, abstract skims, line routing), `standard` (digests, fills) or
`strong`. `Request(model="light")`, `--model light` and `llm.model_id("light")` resolve it for the request's provider via
`llm.tier_model(provider, tier)`: the user's `~/.config/kb-distillery/llm.toml` (`[claude]`, `[openai]`, `[gemini]` tables,
optional `[prices."<id>"]`; example in `kits/base/defaults/llm.example.toml`), else the built-in map (Claude haiku, sonnet, opus).
A tier never changes the backend or the provider.

### Billing

`llm.resolve(provider, backend, kb)` picks the provider and backend for `llm ask` and `doctor`: provider = argument, `$KB_LLM_PROVIDER`, `[llm] provider`
in kb.toml, else automatic (Claude if logged in or keyed, else the first keyed of OpenAI and Gemini); backend = argument,
`$KB_LLM_BACKEND`, else subscription when logged in, API when only a key exists. Only `llm ask` and `doctor` honour the provider
setting so far; other features run on Claude. Digest jobs do not use it: they default to the subscription (when logged in, else the API) for up to `[llm] bulk_threshold` sources
(default 5) and to the API above it; Batch is chosen per job (half price, up to 24 hours). OpenAI and Gemini prices are
unverified. The user-facing explanation is `docs/concepts/llm.md`.
