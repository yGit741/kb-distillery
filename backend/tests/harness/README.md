# Pipeline harness and vault invariants

The safety net for the data-model restructure (stages 3-9). Offline, deterministic, no LLM.

```
pixi run harness                        # end-to-end run on a scratch fixture vault, compared with the goldens (~2 min)
pixi run harness -- --update-goldens    # regenerate backend/tests/fixtures/golden/ (review the diff!)
pixi run harness -- --keep              # leave the scratch vault on disk (path printed)
pixi run harness-invariants -- --out X.json        # numbers + SHA-256 of every page body of THIS checkout (read-only)
pixi run harness-invariants -- --compare backend/tests/fixtures/baseline-invariants.json   # exit 1 on a body change or count regression
pixi run harness-bite                   # proves the harness fails when the pipeline is broken (~4 min)
pixi run test                           # includes the fast unit tests (test_harness_unit.py), not the end-to-end run
```

## What `harness` does

1. `fixture_vault.build(root, inputs, model="legacy")` creates a scratch vault: a copy of the tool code
   (`meta/`, minus vault data) plus a seed wiki (10 topic pages, ideas, one course, one series, one video source),
   and one input file per source kind. `model` selects the front-matter form of the seed pages; only `legacy`
   (the live 16-type model) exists today, a `v2` (type/kind/depth) set is added later without touching the runner.
2. `run_pipeline.py` runs the real path with cwd = the scratch vault: `scrap` -> `catalog` (with collection) ->
   digest -> `lint` -> graph / explorer / chat-retrieval builders -> share build (`kb.share.build --inner`,
   public profile) -> nightly report preview. LLM steps are replaced by recordings in
   `fixtures/recorded/digests.json` (the claims.json the agent would have written, plus the easy-digest summaries).
3. Artifacts are normalised (paths, timestamps, session ids, PDF sha1) and compared with
   `fixtures/golden/` (page files, `corpus.tsv`, `index.md`, graph JSON, explorer index, lint output,
   coherence file, share summary, nightly digest, step list). A mismatch prints a unified diff and exits 1.
   Goldens capture current main's real behaviour: they are the migration safety net, not a spec.

## Coverage by source kind (new vocabulary; the live backend still emits the old names)

| case | path exercised |
|---|---|
| `source-paper-local` | scrap -> catalog (paper stub) -> full-digest (begin, extract, map, draft, finalize) |
| `source-paper-arxiv-style` | same, deep-digest `--confirm-heavy`, page-1 arXiv stamp, arXiv `url:` |
| `source-article-web-clip` | Kalai-style clip -> catalog into a series -> easy-digest, row ticked |
| `source-blog-post-hebrew` | Not-Exact tagged post -> catalog creates the blog page -> easy-digest |
| `source-conversation-email` | `scrap-mail` of an mbox -> catalog -> full-digest |
| `source-ai-chat` | catalog -> chat pipeline (`chat_build` tree + `chat_render` page); the transactional digest is refused by lint for chats |
| `collection-book` | 62-page PDF with an outline -> `full-digest --part 2` -> book hub with partition, Overview written |
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
`<vault>/backend/src/kb/lint/lint.py`. So the scratch vault carries its own copy of the tool code and every command runs with
`cwd=<scratch vault>` and `KB_ROOT` unset. After the `meta/` -> `backend/` move, change `META_SRC`/`CODE_EXCLUDE`
in `fixture_vault.py` and the `-m meta.*` module names in `run_pipeline.py`; nothing else references code layout.

## Vault invariants

`vault_invariants.py` is read-only over any vault. Reported with the NEW words (`type/kind`, `depth`):
page count per `type/kind`, sources per `kind:depth`, links, dangling links, orphans, lint errors/warnings,
open coherence warnings, raws resolvable, collection-table consistency, graph nodes/edges, a share-size
estimate, and the SHA-256 of every page BODY (text after the closing front-matter delimiter, keyed by slug,
independent of type, so it survives the migration unchanged). `legacy_model.py` is the ONE module that maps the
old front matter to type/kind/depth (DELETE after data-model stage 7). `--compare` exits 1 on any body change or
removal, or any count regression (fewer pages/links/graph items/resolvable raws; more dangling/orphans/lint
errors/warnings/open coherence/inconsistent tables).

Partial checkouts (fresh worktree, CI): raw binaries are gitignored, so they are absent from disk. The report says
how many (`raw_binaries_absent`); `raws_resolvable` and lint warnings depend on that, so compare baselines taken
in the same kind of checkout. Lint and the graph snapshot run on a temporary COPY of the vault (lint rewrites
`index.md` / `corpus.tsv`).
