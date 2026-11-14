# Pipeline harness and vault invariants

The safety net for the data-model restructure (stages 3-9). Offline, deterministic, no LLM.

```
pixi run harness                        # end-to-end run on a scratch fixture vault, compared with the goldens (~2 min)
pixi run harness -- --update-goldens    # regenerate tests/fixtures/golden/ (review the diff!)
pixi run harness -- --keep              # leave the scratch vault on disk (path printed)
pixi run harness-invariants -- --out X.json        # numbers + SHA-256 of every page body of THIS checkout (read-only)
pixi run harness-invariants -- --compare X.json    # a baseline you wrote earlier with --out; exit 1 on a body change or count regression
pixi run harness-bite                   # proves the harness fails when the pipeline is broken (~4 min)
pixi run test                           # includes the fast unit tests (test_harness_unit.py), not the end-to-end run
```

## What `harness` does

1. `fixture_vault.build(root, inputs)` creates a scratch vault: a copy of the tool code
   (`src/kb_distillery`, minus tests) plus a seed wiki in schema-1.0 form (10 topic pages, ideas ending with `## My notes`,
   one course, one series, one video source), and one input file per source type.
2. `run_pipeline.py` runs the real path with cwd = the scratch vault: `scrap` -> `catalog` (with collection) ->
   digest -> `lint` -> graph / explorer / chat-retrieval builders -> share build (`kb_distillery.publish.site.build --inner`,
   public profile) -> nightly report preview. LLM steps are replaced by recordings in
   `fixtures/recorded/digests.json` (the claims.json the agent would have written, plus the easy-digest summaries).
3. Artifacts are normalised (paths, timestamps, session ids, PDF sha1) and compared with
   `fixtures/golden/` (page files, `corpus.tsv`, `index.md`, graph JSON, explorer index, lint output,
   coherence file, share summary, nightly digest, step list). A mismatch prints a unified diff and exits 1.
   Goldens capture current main's real behaviour: they are the migration safety net, not a spec.

## Coverage by layer and type (schema 1.0)

| case | path exercised |
|---|---|
| `source-paper-local` | scrap -> catalog (paper stub) -> full-digest (begin, extract, map, draft, finalize) |
| `source-paper-arxiv-style` | same, deep-digest `--confirm-heavy`, page-1 arXiv stamp, arXiv `url:` |
| `source-article-web-clip` | Author-style clip -> catalog into a series -> easy-digest, row ticked |
| `source-blog-post-hebrew` | Not-Exact tagged post -> catalog creates the blog page -> easy-digest |
| `source-conversation-email` | `scrap-mail` of an mbox -> catalog -> full-digest |
| `source-ai-chat` | catalog -> chat pipeline (`chat_build` tree + `chat_render` page); the transactional digest is refused by lint for chats |
| `collection-book` | 62-page PDF with an outline -> catalog builds the book page and its chapters -> `full-digest --chapter 2` -> part page, Overview written |
| `collection-course-member-1/2` | slides catalogued with `--collection`/`--title` -> `full-digest <hub> --row 1`, easy-digest row 2 |
| video | seeded hand-written page (there is no ingest path for videos) |

Also checked: the dedup gate (re-scrapping the same bytes is refused).

## SKIPPED steps (always listed in the report)

network: scrap by URL / arXiv id and arXiv metadata, `scrap-wordpress`, `scrap-gdrive`, IMAP mail, researcher
index; LLM + network: chat answers (retrieval is covered); Cloudflare + a git ref: share outer build, deploy,
snapshots; dashboard HTTP server (builders are called as pure functions); video ingest (no path).

## How the KB root is overridden

`KB_ROOT` is honoured by lint, coherence, semfind, graph/explorer/digestion data and the ingest `paths` module,
but NOT everywhere: `ingest extract` derives the vault from the code location and `finalize` runs
`<vault>/src/kb_distillery/lint/lint.py`. So the scratch vault carries its own copy of the tool code and every command runs with
`cwd=<scratch vault>` and `KB_ROOT` unset. Code layout is referenced only by `CODE_SRC`/`META_COPY` in
`fixture_vault.py` and the `-m kb.*` module names in `run_pipeline.py`.

## Vault invariants

`vault_invariants.py` is read-only over any vault and reads the schema-1.0 front matter directly. Reported:
pages per `layer` and per `layer/type`, sources per `type:depth`, links, dangling links, orphans, lint
errors/warnings, open coherence warnings, raws resolvable, collection-table consistency, graph nodes/edges, a
share-size estimate, and the SHA-256 of every page BODY (text after the closing front-matter delimiter, keyed by
slug, independent of front matter). `--compare` exits 1 on any body change or removal, or any count regression
(fewer pages/links/graph items/resolvable raws; more dangling/orphans/lint errors/warnings/open coherence/inconsistent
tables). Re-baseline (`--out`) after a deliberate wiki change.

Partial checkouts (fresh worktree, CI): raw binaries are gitignored, so they are absent from disk. The report says
how many (`raw_binaries_absent`); `raws_resolvable` and lint warnings depend on that, so compare baselines taken
in the same kind of checkout. Lint and the graph snapshot run on a temporary COPY of the vault (lint rewrites
`index.md` / `corpus.tsv`).
