# {{name}} — agent schema

A knowledge base (`{{kb_id}}`, kit `{{kit}}`) kept by an agent and read by a person. Follows the [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern: raw inputs are digested into a linked wiki.

This file is the core every turn needs. The details live in `.claude/docs/`: read the one the **Doc router** names before you act. The skills live in `.claude/skills/<skill>/SKILL.md`. Both folders are copies from the `{{kit}}` kit, re-synced with `distill init --refresh`; do not edit them here.

**This folder is a knowledge base, not the tooling.** It is its own git repository. The tooling is `kb-distillery` (the `distill` command): it lints, commits and serves this folder. Run `distill doctor` to check the environment and `distill launch` to open the explorer. `raw/`, `wiki/` and `meta/` below are paths inside this folder.

## Folders

| Folder | Path | Rule |
|-------|------|------|
| **Raw** | `raw/` | User-owned inputs. **Immutable: never write here.** New files arrive in `raw/inbox/` and are cataloged into format folders. |
| **Wiki** | `wiki/` | Agent-owned synthesis. Flat. Create, update, cross-link. |
| **Think** | shared `think/` space | Human-owned, schema-free, its own repo. Agents never write here. Distilled pages cite `think:<note>.md`. |
| **Meta** | `meta/` | Metadata: manifest (`corpus.tsv`), log, chats, aliases. A kb's `meta/` overrides the engine's defaults (flags, page templates, digest instructions). No code. |
| **Config** | `kb.toml` | The kb: id, name, schema version, kit, its own page types (`[types]`) and digest instructions (`digest/`). |

## Hard rules

1. **The linter IS the schema (`distill lint`).** Prose rules drift; the linter doesn't. If it passes, the write is legal.
2. Never write in `raw/` or the think space, and never inside a `## My notes` section: that is the user's.
3. Never run raw `git commit` / `push` / `merge` / `tag` / `revert` / `reset` in this repo. Knowledge changes (one `kb(<op>)` commit each; see the `kb-history`, `kb-snapshot` and `kb-undo` skills) go through `distill ops` (a session per operation), which lints, commits one `kb(<op>): …` step and tags `kb-x.y.z`. The hooks in `.claude/` and `core.hooksPath` enforce this and fail closed when `distill` is not on PATH.
4. One transactional workflow (ingest session, ops session, distill) at a time.
5. Pages link with standard relative markdown links, `[Tensor rank](tensor-rank.md)`: the bare `slug.md` (`wiki/` is flat and is the bundle root), `[label](slug.md#heading)` for a heading, never `[[wikilinks]]` (they live only in the user's `## My notes`) and never a path (`wiki/…`, `../wiki/…`). Paths into `raw/` go in backticks, not links.
6. Do not hand-edit `wiki/index.md`, the `wiki/<type>/index.md` section indexes or `meta/corpus.tsv`: all are generated on every lint run. To find a page read `wiki/index.md` (a tiny root), then only the one section index you need. Every `index.md` and `wiki/log.md` are OKF's reserved files, not pages.
7. **`digest` alone → ask the tier (easy / full / deep).** Bare "digest" never triggers `full-digest`.
8. **Dedup:** always `distill ingest resolve` before `scrap`. If FOUND → cite `[Title](slug.md)`; do not re-download.
9. Read a skill's `SKILL.md` before running it.
10. **Every LLM call goes through `kb_distillery.llm`**: one `--backend subscription|api|batch` choice (`$KB_LLM_BACKEND`, default subscription). Never add a `claude -p`, SDK or HTTP call of your own. CLI: `distill llm ask|submit|status|collect`.

## Intent router — casual requests → skills

Map what the user says to a skill before acting, read that skill's `SKILL.md`, then follow it.

| The user says… | Do | Lands as |
|---|---|---|
| "what do I know about … / where did I read … / compare …" | `query-knowledge` (read-only) | nothing |
| "which sources do I have on … / what does this undigested source say / is it worth digesting" | `explore-raw-data` (read-only) | nothing |
| "save / scrap <url or file>" | `scrap-data` | `kb(import)` |
| "catalog / triage the inbox" | `ingest-to-catalog` | `kb(catalog)` |
| "digest <source>" (no tier) | **ask**: easy, full or deep | — |
| "skim / easy-digest", "full-digest", "deep-digest" (+ confirm heavy) | that digest skill → `semantic-lint-hop` | `kb(digest)` |
| "split / merge / rename / fix this note", "file that answer back": anything in `wiki/` | `wiki-edit` (`distill ops begin` … `commit`) | `kb(refine)` |
| "distill my think note …" | `distill-think` | `kb(distill)` |
| "propose relations / typed edges" | `propose-relations` | `kb(refine)` |
| "audit this topic page" | `lint-moc` | nothing, or `kb(refine)` |
| "undo that / revert the split" | `kb-undo` (confirm the step first) | `kb(undo)` |
| "snapshot / freeze" · "go back to kb-x.y.z" | `kb-snapshot` | tag · `kb(restore)` |
| "what changed / kb status / which version" | `kb-history` | nothing |
| "share / export for an LLM" (a zip of the text) | `export-kb` | zip |

When the request is unclear, ask one short question.

## Doc router — when you are about to… → read

| When you are about to… | Read |
|---|---|
| write or check a wiki page: layers, `type:` / `depth:`, frontmatter, filename prefixes, note sections, `## My notes`, person pages | `.claude/docs/page-model.md` |
| change `[kb] kit`, `[types]` or `[edges]` in `kb.toml`: what a kb may extend, what it may not | `.claude/docs/kits.md` |
| publish or share the kb as a site, or set `[publish]` | `.claude/docs/publish.md` |
| read or write raw sources from code, or set `[storage]` | `.claude/docs/storage.md` |
| touch `raw/` or `meta/corpus.tsv`: format folders, inbox, dispositions, file naming | `.claude/docs/raw-and-corpus.md` |
| work on a course / series Contents table, digest a collection row, or digest a book | `.claude/docs/collections.md` |
| send a think note into kbs, or cite `think:` | `.claude/docs/think.md` |
| pick a skill tier or run the ingest / query / distill CLIs | `.claude/docs/workflows.md` |
| handle coherence warnings or semantic lint | `.claude/docs/semantic-lint.md` |
