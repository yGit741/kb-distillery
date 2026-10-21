# Thesis Wiki — agent schema

Personal knowledge base for an MSc in theoretical ML. **The thesis topic is not yet chosen** — the vault exists to explore candidate directions and decide. Follows the [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern.

## Layers

| Layer | Path | Rule |
|-------|------|------|
| **Raw** | `raw/` | User-owned inputs. **Immutable — never write here.** |
| **Wiki** | `wiki/` | Agent-owned synthesis. Flat. Create, update, cross-link. |
| **Think** | `think/` | Human-owned slow space. Schema-free. Agents never write here. |
| **Meta** | `meta/` | Schema, templates, log. |

```
raw/inbox/            reMarkable sync target. Any shape. MUST drain to zero.
raw/papers/<course>/  academic PDFs
raw/slides/<course>/  lecture decks, presentations
raw/notes/<course>/   handwritten notes, recaps, scratch
raw/mail/<thread>/    email thread bundle (thread.md + flat attachments)
raw/web/  raw/assets/ clips, images (flat)
raw/chats/             LLM chat exports (flat)
wiki/                 flat agent-owned notes
think/                human slow space (not linted)
_quarantine/          staged for deletion, gitignored, not part of the vault
```

## meta/lint.py IS the schema

Prose rules drift; this doesn't. If `python3 meta/lint.py` passes, the write is legal.

**Environment:** one-time `curl -fsSL https://pixi.sh/install.sh | bash`, then restart the shell. All tasks below work via `pixi run <task>`.

```
pixi run lint                      check + reconcile + regenerate index.md
pixi run health                    terminal health summary
pixi run dashboard                 localhost health UI + graph explorer (http://127.0.0.1:8765, /graph, /digestion)
pixi run launch                    restart dashboard from current code (detached) + open browser
pixi run lint-strict               ingest-finalize checks
pixi run ingest-status             open ingest sessions
pixi run distill-propose -- <slug> propose graph brief from think page
pixi run distill-apply -- <slug>   apply distill plan to public KB
pixi run lint-skills               validate skill definitions
pixi run sync-skills               copy meta/skills/ → .cursor/skills/ (after lint-skills)
pixi run export-kb                 zip wiki + think → .exported/ (LLM share)
pixi run lanes                     pending changes per git lane
pixi run ops -- status             knowledge version, sessions, hooks (also: log, snapshot, undo, restore)
pixi run ops -- record <op> <target> "summary" <paths…>   commit already-modified knowledge as one op
pixi run ship -- prune [--apply]   delete merged infra/* and worktree-* branches
pixi run daily-sync                nightly: commit think/ edits + leftovers, push main + tags
pixi run ship -- start|commit|pr|merge   tooling via infra/<feature> PRs (on demand)
pixi run install-hooks             use meta/githooks (commit-msg, pre-commit, pre-push)
pixi run install-sync              install nightly daily-sync launchd job
```

Without pixi, use `python3` equivalents (`python3 meta/lint.py`, `python3 -m meta.dashboard`, …).

**Write guardrails:** `meta/guard.py` blocks illegal agent writes via preToolUse hooks in both `.cursor/hooks.json` (Cursor) and `.claude/settings.json` (Claude Code). Keep both pointed at the same script. `CLAUDE.md` imports this file for Claude instruction parity.

**Commit gate:** `meta/githooks/` (`pixi run install-hooks`): `pre-commit` runs `meta/lint.py` (+ `lint_skills.py` for tooling), `commit-msg` and `pre-push` run `meta/commit_policy.py`. Do not hand-edit `index.md` or `meta/corpus.tsv` — both are generated on every lint run. `python3 meta/lint.py --health` or `python3 -m meta.dashboard` for vault health.

**Git lifecycle — KB Conventional Commits.** Lane membership lives in `meta/schema.py` (`KNOWLEDGE_PATHS`, `TOOLING_PATHS`, `lane_of`). The dashboard **Lifecycle** tab explains and shows all of it.

| Track | Paths | Committed as | By |
|-------|-------|--------------|----|
| knowledge | `wiki/ think/ raw/ index.md meta/{corpus,coherence-warnings,aliases}.tsv meta/log.md meta/chats/` | `kb(<op>): <summary> (kb-x.y.z)` **directly on main, one commit per operation** — ops: `import catalog digest refine distill think undo restore`; trailers `KB-Version KB-Op KB-Target` (+`KB-Reverts`, `KB-Snapshot`) | writer CLIs (`meta.ingest`, `meta.distill`) automatically; free-form wiki edits via `pixi run ops -- begin …` / `commit` (skill `wiki-edit`); your `think/` edits as `kb(think)` before each op and nightly |
| tooling | `meta/` (code, skills, dashboard, docs), `.cursor/ .claude/ .vscode/`, `pixi.*`, root `*.md`, `.gitignore` | `schema|feat|fix|chore|paradigm(<component>): <imperative summary>` on `infra/<feature>` (scope always required; docs/tests/refactors are `chore`), merged as a merge commit `… (#N)` that takes the highest type of its commits — **never squash** | `pixi run ship -- start/commit/pr/merge` (skill `infra-pr`) — whenever the user asks for a fix/change/feature; **merge only on their OK** |
| other | anything else | never committed — `pixi run lanes` lists it; gitignore, move or delete | — |

**Versions are knowledge-only:** `kb-x.y.z` — x paradigm, y schema (`SCHEMA_VERSION` in `meta/schema.py`), z step (computed). Tooling is unversioned; a `schema`/`paradigm` PR carries its migration (`meta/migrations/`, `pixi run ops -- migrate` on the branch), snapshots first and bumps y/x on merge. **Snapshots** are annotated tags `kb-x.y.z` (`pixi run ops -- snapshot "label"`). **Undo** one step: `pixi run ops -- undo <sha>`; **restore** a snapshot: `pixi run ops -- restore kb-x.y.z` — both new commits that rewrite only `wiki/`, `meta/aliases.tsv`, `meta/chats/` (never `raw/`, `think/`, `meta/log.md`, generated files) and only on the user's request.

Agents never run raw `git commit`/`push`/`merge`/`tag`/`revert`/`reset` or `gh pr` — `.cursor/hooks/block-git-write.sh` (→ `meta/git_guard.py`, both Cursor and Claude Code) allows only a single `pixi run ops|ship|daily-sync|…` invocation. `meta/guard.py` warns on wiki writes without an open ops session (blocks once `OPS_STRICT`). Feature work shouldn't touch knowledge paths, except a schema PR's migration.

**Nightly schedule:** `pixi run install-sync` installs `meta/launchd/com.thesis-kb.daily-sync.plist` into `~/Library/LaunchAgents/` (log: `~/Library/Logs/thesis-kb-daily-sync.log`). It must run on this Mac — a cloud agent can't see local edits. See [`meta/automation-daily-sync.md`](automation-daily-sync.md).

## Intent router — casual requests → skills

Map what the user says to a skill before acting; read that skill's `SKILL.md`, then follow it. A casual request **is** the ask: "fix the graph legend" means start the PR flow, not "suggest a fix".

| The user says… | Do | Lands as |
|---|---|---|
| "fix / change / add / improve … the dashboard, explorer, graph, ingest, CLI, a skill, lint" — anything in tooling | `infra-pr`: `ship start <feature> --worktree` → implement → `ship commit "fix\|feat\|chore(<component>): …"` → `ship pr` → give the link. **Merge only when the user says merge** (or "fix and merge") | PR `… (#N)` |
| "new note type / new field / lint should require …" | `infra-pr` as a **schema** PR: bump `SCHEMA_VERSION`, add `meta/migrations/NNNN_*.py`, `ops migrate` on the branch | PR, bumps y |
| "what do I know about … / where did I read … / compare …" | `query-kb` (read-only) | nothing |
| "add researcher <name>" / "index <name>'s papers" | `build-researcher-profile` | `kb(catalog)` |
| "save / scrap <url or file>" | `scrap-data` | `kb(import)` |
| "catalog / triage the inbox" | `ingest-to-catalog` | `kb(catalog)` |
| "digest <paper>" (no tier) | **ask**: easy, full or deep | — |
| "skim / easy-digest", "full-digest", "deep-digest" (+ confirm heavy) | that digest skill → `semantic-lint-hop` | `kb(digest)` |
| "split / merge / rename / fix this note", "file that answer back" — anything in `wiki/` | `wiki-edit` (`ops begin` … `ops commit`) | `kb(refine)` |
| "distill my think note …" | `distill-think` | `kb(distill)` |
| "undo that / revert the split" | `kb-undo` (confirm the step first) | `kb(undo)` |
| "snapshot / freeze" · "go back to kb-x.y.z" | `kb-snapshot` | tag · `kb(restore)` |
| "what changed / kb status / which version" | `kb-history` | nothing |
| "share the KB / export for an LLM" | `export-kb` | zip |
| "create a skill / new workflow" | `create-skill` → `infra-pr` | PR |

**Tooling or knowledge?** The target decides: files under `wiki/`, `raw/`, `think/` are knowledge (ops, straight to main); code, skills, dashboard, docs and config are tooling (PR). When one request touches both, ship the tooling PR first, then do the knowledge step on main. When the target is unclear, ask one short question.

## Frontmatter

```yaml
type: concept | question | person | paper | book | part | source | moc | distilled-think
status: seed|growing|solid   (question: open|partial|resolved; paper/book/part: to-read|reading|digested; distilled-think: review|applied|archived)
digestion-status: catalog|easy|full|deep   # papers and book parts — depth of write-up
area: [info-theory]          # papers/books/parts: theme slugs only (whitelist in meta/schema.py THEME_SLUGS)
related: [tensor-rank]       # bare slugs — wiki/ is flat, so no paths
raw: raw/papers/x/y.pdf      # paper/source/book/part; `none` + a `url:` if read externally
book_pages: 419              # book only — total PDF pages
book: <book-slug>            # part only — its hub; plus section: and section_pages: A-B
```

Wikilinks are always bare: `[[tensor-rank]]`, never `[[concepts/tensor-rank]]`. Paths into `raw/` go in backticks, not wikilinks.

## The corpus manifest

`meta/corpus.tsv` has one row per file in `raw/`. Nothing can be silently forgotten.

| disposition | meaning |
|-------------|---------|
| `queued` | keep, not yet written up — **the real backlog** |
| `digested` | a wiki page cites it via `raw:` |
| `partial` | **a book with only some chapters digested** — the rest is still backlog |
| `skip` | explicitly not worth a note (a decision, not neglect) |
| `dupe:<path>` | superseded by another file |
| `ink:<path>` | reMarkable annotation overlay belonging to `<path>` |

The linter maintains it: a new file appears as `queued`; a file gone from disk is removed; **a sha1 change on a `digested` file re-opens it as `queued`** — so re-annotating a paper on the tablet automatically re-queues it.

## Naming

`raw/papers/` uses **`<year>-<kebab-title>.pdf`** — lowercase, hyphens, no spaces. Sortable, greppable, and the year is metadata you would otherwise have to open the file to find.

```
2023-toolformer.pdf
1948-a-mathematical-theory-of-communication.pdf
```

The linter enforces the pattern and cross-checks the filename year against the digest's `year:` frontmatter, so the two cannot drift apart.

Non-paper sources are named **by origin**: `<source>-<sub-source>-<topic>`, lowercase ASCII kebab.

| Origin | Pattern | Example |
|---|---|---|
| לא מדויק blog (gadial.net) | `blog-not-exact-<post>` | `blog-not-exact-jordan-form-in-practice.md` |
| Linear Algebra 1 | `linear-algebra-1-<daniel-notes-on-maman\|course-book\|theorem-and-definitions>-<topic>` | `linear-algebra-1-daniel-notes-on-maman-01.pdf` |
| Linear Algebra 2 | `linear-algebra-2-course-book-<part>` | `linear-algebra-2-course-book-part-a.pdf` |

Provenance is kept, not lost: the original name lives in `meta/raw-renames.tsv` (old → new, applied by `meta/rename_raw.py`, which also carries `corpus.tsv` rows and rewrites wiki references) and, for `.md`, in frontmatter `original_name`/`title`/`aliases`. Raw `.md` files carry filter tags — `source/blog-not-exact`, `source/course-book`, `source/daniel-notes-on-maman`, `source/theorem-and-definitions`, `subject/<x>`, `course/<x>`; PDFs are filtered by filename prefix (`file:linear-algebra-1-`). Other notes, lecture decks, chats and mail still keep their original names until migrated the same way.

⚠️ reMarkable's `X (annotations).pdf` exports are **ink-only overlays**, not annotated documents — typically a few KB against a multi-MB source, and unreadable on their own. They have all been deleted. If new ones appear, do not delete the source document in their favour.

## Note sections

- **concept** — One-liner → Intuition → Formal → Why it matters → Connections → Open questions
- **question** — Question → Why it matters → What would answer it → Current state → Links
- **paper** — Problem → Method → Result → Why it matters here → Connections
- **book** — Overview (≥1 paragraph, required) → Partition → Key concepts → Threads. A hub node, not a reading unit
- **part** — as paper, plus a `> Part of [[book]] · pp. A–B` line under the title
- **moc** — Scope → Key concepts → Raw material → Threads (research themes only)
- **distilled-think** — Summary (review prose) → Proposed propagation → Not promoting (transient; use `--cleanup` after apply)
- **source** — Scope → Key concepts → Raw material → Threads (course provenance)

## Theme whitelist (paper `area:`)

`statistics`, `optimization-theory`, `learning-theory`, `info-theory`, `implicit-regularization`, `tensor-factorization`, `complex-nn`, `quantum`, `boolean-analysis`, `fourier-analysis`. Course slugs use `source-*` pages, not MOCs.

## Semantic lint

**Structural lint** (`meta/lint.py`): links, schema, inbox — unchanged.

**Semantic lint** (`meta/coherence.py`): meaning-level checks, 0 LLM.

| kind | meaning | action |
|------|---------|--------|
| `internal` | bad ingestion — wiki stale/wrong vs source | **fix** (re-digest / edit); score ≥ 70 → lint ERROR |
| `external` | two digested papers disagree | **note** on each paper's `## Connections` / `## Links out` |
| `cosmetic` | graph hygiene | warn only |

```
python3 meta/coherence.py status
python3 meta/coherence.py fixed <id>    # internal resolved
python3 meta/coherence.py noted <id>    # external recorded on paper
python3 meta/coherence.py dismiss <id>
python3 meta/semfind.py moc moc-info-theory
```

Manifest: `meta/coherence-warnings.tsv` (regenerated on lint; statuses persist).

After full/deep digest or distill apply: `SEMFIND_READY` → `meta/skills/semantic-lint-hop/SKILL.md`. On-demand theme pass: `meta/skills/lint-moc/SKILL.md`.

## Distill think

Human writes in `think/*.md` (schema-free). Distill produces a transient `wiki/distilled-think-*.md` for review, then patches the public KB on apply.

```
python3 -m meta.distill propose <think-file>              # → distilled-think page + plan.json
python3 -m meta.distill revise <think-file>               # re-read think/, keep edited Summary
python3 -m meta.distill apply <think-file> --cleanup       # propagate + delete distilled page
python3 -m meta.distill abort <think-file>
```

`think/` is never agent-edited. See `meta/skills/distill-think/SKILL.md`.

## Skill ladder

Read `meta/skills/README.md` (§ Adding a skill) before any workflow. Run `pixi run lint-skills` then `pixi run sync-skills` after editing skills.

| Skill | LLM tier | Budget (in) | Trigger |
|-------|----------|-------------|---------|
| `scrap-data` | none | 0 | scrap, download, save to inbox, pull from google drive |
| `ingest-to-catalog` | none | 0 | catalog, triage inbox, drain inbox |
| `easy-digest` | light | ~2–4k | `easy-digest`, `easy digest`, `skim` |
| `full-digest` | medium | ~8–12k | `full-digest`, `full digest` only |
| `deep-digest` | heavy | ~25–40k+ | `deep-digest` + user confirms heavy |
| `distill-think` | medium | ~8–12k propose | `distill-think`, `distill think`, `graph brief` |
| `export-kb` | none | 0 | `export-kb`, `export kb`, `share kb` |
| `query-kb` | light–medium | ~3–15k | `query-kb`, `query kb`, `what do I know about` |
| `semantic-lint-hop` | light–medium | ~3–12k | after full/deep digest finalize or distill apply |
| `lint-moc` | medium | ~8–20k | `lint-moc`, `lint moc` |
| `build-researcher-profile` | light | ~3–8k verify | `build researcher profile`, `index researcher` |
| `create-skill` | none | 0 | create skill, new skill (meta; not in digest ladder) |

**`digest` alone → ask tier (easy / full / deep).** Bare "digest" never triggers `full-digest`.

**Dedup:** always `resolve` before `scrap`. If FOUND → cite `[[slug]]`; don't re-download.

```
python3 -m meta.ingest resolve <url|arxiv|slug> # check vault first (0 LLM)
python3 -m meta.ingest scrap <url>              # → raw/inbox/ (blocked if duplicate)
python3 -m meta.ingest scrap-mail <mbox-or-eml> # → raw/inbox/mail-.../ (thread + attachments)
python3 -m meta.ingest scrap-gdrive --dry-run   # preview a mounted Drive folder pull (0 bytes)
python3 -m meta.ingest catalog <inbox-path>     # → raw/papers/ + wiki stub
python3 -m meta.ingest easy-digest <slug|raw>   # light abstract skim
python3 -m meta.ingest full-digest <raw>        # medium: begin→finalize
python3 -m meta.ingest deep-digest <raw> --confirm-heavy
python3 -m meta.ingest toc <raw>                # book partition (or a proposed one) (0 LLM)
```

**Books are a hub plus parts.** A PDF of ≥60 pages is a book. It gets one `type: book` page
(slug = the PDF basename) holding an `## Overview` paragraph and a `## Partition` table that splits
pages `1..book_pages` into **disjoint, exhaustive parts** — a part can be a chapter, merged short
chapters or half a long one; front/back matter rows are `skip`. Each digested part is its own
`type: part` page (slug `<book-slug>-<topic>`); undigested parts are table rows, not pages.

```
| # | Part | Pages | Status | Note |
|---|------|-------|--------|------|
| 1 | Front matter · Prefaces | 1–18 | skip | |
| 2 | Chapter 1. Boolean functions and the Fourier expansion | 19–42 | full | [[2014-analysis-of-boolean-functions-ch1-fourier-expansion]] |
| 3 | Chapter 2. Basic concepts and social choice | 43–68 | — | |
```

Digesting a book is always scoped — the CLI prints the partition and exits 2 instead of guessing:

```
python3 -m meta.ingest toc <raw>                     # partition [x]/[ ]/[-]; --depth 2 adds the outline
python3 -m meta.ingest full-digest <raw> --part 3    # a row of the partition
python3 -m meta.ingest full-digest <raw> --pages 43-55  # carves a new part out of undigested rows
python3 -m meta.ingest full-digest <raw> --section 2 # an outline entry (chapter number, #index, text)
python3 -m meta.ingest full-digest <raw> --whole-book  # override the gate (writes a paper)
```

The first scoped digest creates the book page from `meta/templates/book.md` with a partition
proposed from the PDF outline (split only at chapter/section boundaries, ≤60 pp per part); write
its Overview by hand. `finalize` writes the `type: part` page and ticks its row. A part's identity
is its page range — the `#` column is display order and renumbers when a row is split.

**The partition is the truth** (`meta/books.py`, checked by lint): gaps or overlaps are errors,
a part over 60 pages is a warning, a digested row must link its part page and match its
`digestion-status`, and the part's `book:`/`raw:`/`section_pages:` must agree with its row.
Coverage = digested pages ÷ non-skip pages; below 100% the raw file is `partial` in
`meta/corpus.tsv` — never `digested` — warns on every run and counts in `--health` as
`partial-books`. The book's `status` follows coverage. Re-digesting a finished part is refused.

During `full-digest` / `deep-digest`, `meta/guard.py` blocks direct writes to session-owned wiki paths — use `draft` + `finalize`. Legacy `reingest-*` is bootstrap-only.

**Triage:** anything in `raw/inbox/` gets cataloged or deleted. The inbox is a queue, not storage.

**Query:** Karpathy Query operation — read wiki, cite `[[slugs]]`, file good answers back on request. See `meta/skills/query-kb/SKILL.md`.

```
python3 meta/query.py candidates "<keywords>"   # rank slugs (0 LLM)
python3 meta/query.py mocs                      # theme entry points
```

Workflow: `index.md` → `candidates` → read 3–8 pages → synthesize. Not the same as `meta.ingest resolve` (ingest dedup).
