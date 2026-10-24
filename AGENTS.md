# Thesis Wiki — agent schema

Personal knowledge base for an MSc in theoretical ML. **The thesis topic is not yet chosen** — the vault exists to explore candidate directions and decide. Follows the [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern.

## Folders

| Folder | Path | Rule |
|-------|------|------|
| **Raw** | `raw/` | User-owned inputs. **Immutable — never write here.** |
| **Wiki** | `wiki/` | Agent-owned synthesis. Flat. Create, update, cross-link. |
| **Think** | `think/` | Human-owned slow space. Schema-free. Agents never write here. |
| **Meta** | `meta/` | Vault metadata: manifest, log, templates, chats. No code (see Code layout). |

```
raw/inbox/              the single unclassified queue. Any shape. Drains (warn >30 days, error ≥50 files)
raw/printed-docs/       typed: papers, books, course books, typed notes, blog posts
raw/handwritten/        by hand: reMarkable notebooks, handwritten summaries
raw/presentations/      slide decks (pdf, pptx, key)
raw/llm-chats/          LLM conversation exports (md)
raw/emails/<YYYY-MM-DD-thread>/  thread.md + attachments + parsed.md sidecar — the only nested folder
raw/web-clips/          Web Clipper pages (md, html)
raw/images/             screenshots, figures
wiki/                   flat agent-owned notes; filename prefix = type
think/                  human slow space (not linted)
_quarantine/            staged for deletion, gitignored, not part of the vault
```

`raw/` is split by **format** (how the bytes were produced), never by course or person, and is flat
below the format folder. Split rule: typed → `printed-docs/` (even if annotated), by hand →
`handwritten/` (catalog detects this from the PDF text layer), slides → `presentations/` whatever
the extension. Membership lives in the corpus `collection` column — **a raw file never moves after
catalog**; reclassifying it means editing that cell.

## Code layout

Code, tools and the vault are separate top-level folders; `meta/` is vault metadata only.

```
backend/                Python app, package `kb` (src layout, pyproject.toml, editable install via pixi)
  src/kb/paths.py       the ONE vault-root resolver (KB_ROOT, else this checkout) + every data path constant
  src/kb/core/          schema, graph, hubs, scopes, persons, books, mathnorm, coherence, health
  src/kb/lint/          lint, lint_skills            src/kb/search/       query, semfind, explore_raw, citations
  src/kb/ingest|distill|ops|report|share/            src/kb/git/          guard, git_guard, commit_policy, ship, merge_nudge, curate_history
  src/kb/maintenance/   daily_sync, notify, sync_skills, rename_raw, migrate_model, export, fix_math
  src/kb/migrations/    schema migrations (code); the applied ledger stays in meta/migrations/applied.tsv
  src/kb/services/      former dashboard *_data modules (graph, pages, corpus, scopes, chat, pipeline, lifecycle, ops)
  src/kb/api/           FastAPI app (`pixi run app`): routers/ auto-discovered, models/, sse.py, security.py; README.md = add-a-router recipe
  src/kb/dashboard/     legacy HTML pages + server until their screens are ported (served behind kb.api's catch-all)       src/kb/prompts/  chat prompts
  tests/                pytest, mirrored by package (tests/harness = the pipeline harness)
share/                  Cloudflare Worker (auth.js, admin.js, wrangler template) + its node tests
skills/                 agent skill sources (synced to .cursor/skills and .claude/skills)
tools/                  githooks/, launchd/, launch.sh, restructure/ (the script that made this layout)
meta/                   VAULT METADATA ONLY: corpus.tsv, log.md, aliases.tsv, coherence-warnings.tsv, raw-renames.tsv,
                        chats/, templates/, migration/, migrations/applied.tsv, ops/sync.toml, thesis.md
```

`pixi run api-schema` regenerates `frontend/src/api/schema.d.ts` from the API's OpenAPI (`api-schema-check` fails if stale).
Run a module with `python -m kb.<package>.<module>` (pixi tasks do); `kb` is installed editable, so `pixi install`
again after pulling this layout. Never `sys.path.insert`; take paths from `kb.paths`.

## The linter IS the schema (`kb.lint.lint`)

Prose rules drift; this doesn't. If `python3 -m kb.lint.lint` passes, the write is legal.

**Environment:** one-time `curl -fsSL https://pixi.sh/install.sh | bash`, then restart the shell, then `pixi install` (again after any `pixi.toml` change — the Chat tab's agent backend needs the `claude-agent-sdk` PyPI package; behind a TLS-inspecting proxy run it with `SSL_CERT_FILE` pointing at a PEM of the keychain roots). All tasks below work via `pixi run <task>`.

```
pixi run lint                      check + reconcile + regenerate index.md
pixi run health                    terminal health summary
pixi run dashboard                 localhost health UI + graph explorer (http://127.0.0.1:8765, /graph, /digestion, /ops, /chat — a read-only research agent over the Claude Agent SDK, with the direct Messages call as fallback; pays with a stored API key (`~/.config/thesis-kb/keys/<name>`, switchable in the Session card) or, agent backend only, the `claude login` subscription)
pixi run launch                    restart dashboard from current code (detached) + open browser
pixi run lint-strict               ingest-finalize checks
pixi run ingest-status             open ingest sessions
pixi run distill-propose -- <slug> propose graph brief from think page
pixi run distill-apply -- <slug>   apply distill plan to public KB
pixi run test-e2e                  graph page mouse/keyboard scheme in headless Chromium (needs the playwright npm package)
pixi run lint-skills               validate skill definitions
pixi run sync-skills               copy skills/ → .cursor/skills/ (after lint-skills)
pixi run export-kb                 zip wiki + think → .exported/ (LLM share)
pixi run share -- deploy-main      build main → private Cloudflare site (also: status, rollback, --dry-run)
pixi run share -- snapshot <name> <ref>   audit + publish a PUBLIC snapshot Worker (also: audit, list, history, remove, prune;
                                   `--replace` updates a sent snapshot at the same link, `rollback --worker <name>` undoes it)
pixi run lanes                     pending changes per lane + nightly sync, stale worktrees, open PRs
pixi run ops -- status             knowledge version, sessions, hooks (also: log, snapshot, undo, restore)
pixi run ops -- record <op> <target> "summary" <paths…>   commit already-modified knowledge as one op
pixi run ops -- sync --prefer local|origin [--root <checkout>]   diverged main: replay local kb steps on origin/main keeping one side's text in conflicts
pixi run ship -- prune [--apply]   delete merged infra/*, worktree-*, history/* branches + their clean worktrees
pixi run daily-sync                nightly: commit think/ edits + leftovers, push main + tags, then hygiene checks
pixi run hygiene                   git/ops hygiene report (stale worktrees, unpruned branches, unpushed steps, sessions, PRs, site, snapshots); --json
pixi run nightly-report            preview the nightly report mail (threads, findings, last 24 h); -- --html FILE / --json / --send; live at /ops in the dashboard
pixi run notify-test               send a one-line test email (Gmail app password from the keychain, see meta/ops/sync.toml)
pixi run ship -- start|commit|pr|merge   tooling via infra/<feature> PRs (on demand)
pixi run install-hooks             use tools/githooks (commit-msg, pre-commit, pre-push)
pixi run install-sync              install nightly daily-sync launchd job
```

Without pixi, use `python3` equivalents (`python3 -m kb.lint.lint`, `python3 -m kb.dashboard`, …).

**Write guardrails:** `backend/src/kb/git/guard.py` blocks illegal agent writes via preToolUse hooks in both `.cursor/hooks.json` (Cursor) and `.claude/settings.json` (Claude Code). Keep both pointed at the same script. Claude Code also runs `backend/src/kb/git/merge_nudge.py` on `Stop` (merge reminder; Cursor has no stop hook, so there the skill rule alone applies). `CLAUDE.md` imports this file for Claude instruction parity.

**Partial checkouts:** raw binaries are gitignored, so a clone, a CI run or a fresh worktree lacks them. Lint detects this (≥5 manifest rows of binaries missing from disk, or `KB_CI=1`) and keeps those rows exactly as committed instead of dropping them; everything on disk reconciles as usual. Fewer missing files count as a deliberate deletion.

**Commit gate:** `tools/githooks/` (`pixi run install-hooks`): `pre-commit` runs `backend/src/kb/lint/lint.py` (+ `lint_skills.py` for tooling), `commit-msg` and `pre-push` run `backend/src/kb/git/commit_policy.py`. Do not hand-edit `index.md` or `meta/corpus.tsv` — both are generated on every lint run. `python3 -m kb.lint.lint --health` or `python3 -m kb.dashboard` for vault health.

**Git lifecycle — KB Conventional Commits.** Lane membership lives in `backend/src/kb/core/schema.py` (`KNOWLEDGE_PATHS`, `TOOLING_PATHS`, `lane_of`). The dashboard **Lifecycle** tab explains and shows all of it.

| Track | Paths | Committed as | By |
|-------|-------|--------------|----|
| knowledge | `wiki/ think/ raw/ index.md meta/{corpus,coherence-warnings,aliases}.tsv meta/log.md meta/chats/` | `kb(<op>): <summary> (kb-x.y.z)` **directly on main, one commit per operation** — ops: `import catalog digest refine distill think undo restore`; the summary says what was done in words (slugs become words, cut at a word), the body lists the wiki pages touched; trailers `KB-Version KB-Op KB-Target` (a slug, never a hash) (+`KB-Reverts`, `KB-Snapshot`, `KB-Tier easy\|full\|deep` on digests) | writer CLIs (`kb.ingest`, `kb.distill`) automatically; free-form wiki edits via `pixi run ops -- begin …` / `commit` (skill `wiki-edit`); your `think/` edits as `kb(think)` before each op and nightly |
| tooling | `meta/` (code, skills, dashboard, docs), `.cursor/ .claude/ .vscode/ .github/`, `pixi.*`, root `*.md`, `.gitignore` | `schema|feat|fix|chore|paradigm(<component>): <imperative summary>` on `infra/<feature>` (scope always required; docs/tests/refactors are `chore`), merged as a merge commit `… (#N)` whose body lists the branch's commits; the title takes the highest type of its commits (paradigm › schema › feat › fix › chore — `ship pr`/`merge` refuse a lower one), whole subject ≤ 100 chars — **never squash**; main is merged into the branch only when it gained more than kb steps | `pixi run ship -- start/commit/pr/merge` (skill `infra-pr`) — whenever the user asks for a fix/change/feature; **the agent merges by default**, a `hold`-labelled PR (schema/paradigm, or `pr --hold`) waits for the user's `ship approve N` |
| other | anything else | never committed — `pixi run lanes` lists it; gitignore, move or delete | — |

**Versions are knowledge-only:** `kb-x.y.z` — x paradigm, y schema (`SCHEMA_VERSION` in `backend/src/kb/core/schema.py`), z step (computed). Tooling is unversioned; a `schema`/`paradigm` PR carries its migration (`backend/src/kb/migrations/`, `pixi run ops -- migrate` on the branch), snapshots first (`pre-<feature>`) and again after the merge (`post-<feature>`, the new baseline) and bumps y/x. Schema 1.0 (the source model, see Page layers) was a paradigm PR: kb-1.0.0.

**Merge by default, hold by exception:** agents run `ship merge` themselves once the gates pass. `ship pr` labels every schema/paradigm PR `hold`, and `ship pr --hold` holds any PR the user wants to review ("don't merge", "let me look first"); `ship merge` refuses a held PR and only `ship approve N` — blocked for agents by `git_guard`, so the user types `! pixi run ship -- approve N` — lifts it. **A held PR is never silent:** while one is open, every agent reply ends with `Awaiting your merge: #N <title> <url> — run \`! pixi run ship -- approve N\` …` (a PR is always `#N title`, never a bare number); the Claude Code `Stop` hook (`backend/src/kb/git/merge_nudge.py`, `.claude/settings.json`) bounces a reply that forgot it, once.

**Diverged main** (two sessions pushed the same pages from different bases): `ops sync` fast-forwards or replays unpushed `kb(...)` steps and aborts on a conflict; only the user's `--prefer local|origin` picks a side (a rebase `-X` strategy, whole conflicting hunks), and `--root` lets a worktree run it against the primary checkout. Generated files are rebuilt by the next lint.

**Hygiene is built in, never a gate:** every `kb(...)` step pushes main right away (`--no-push` / `KB_NO_PUSH=1` to defer; the nightly sync is the backstop and `ops status` says whether it is installed and when it last ran); `ship merge` removes its own worktree and local branch; `ship prune --apply` removes merged, clean worktrees and never touches dirty ones; `pixi run lanes` lists stale worktrees, `worktree-*` session branches and open PRs. `.obsidian/` is tooling too, with only `app`, `core-plugins` and `community-plugins` tracked (the rest is gitignored). **Snapshots** are annotated tags `kb-x.y.z` (`pixi run ops -- snapshot "label"`). **Undo** one step: `pixi run ops -- undo <sha>`; **restore** a snapshot: `pixi run ops -- restore kb-x.y.z` — both new commits that rewrite only `wiki/`, `meta/aliases.tsv`, `meta/chats/` (never `raw/`, `think/`, `meta/log.md`, generated files) and only on the user's request.

Agents never run raw `git commit`/`push`/`merge`/`tag`/`revert`/`reset` or `gh pr` — `.cursor/hooks/block-git-write.sh` (→ `backend/src/kb/git/git_guard.py`, both Cursor and Claude Code) allows only a single `pixi run ops|ship|daily-sync|…` invocation. `backend/src/kb/git/guard.py` warns on wiki writes without an open ops session (blocks once `OPS_STRICT`). Feature work shouldn't touch knowledge paths, except a schema PR's migration.

**Nightly schedule:** `pixi run install-sync` installs `tools/launchd/com.thesis-kb.daily-sync.plist` into `~/Library/LaunchAgents/` (log: `~/Library/Logs/thesis-kb-daily-sync.log`). It must run on this Mac — a cloud agent can't see local edits. After the sync it runs the hygiene checks (`backend/src/kb/ops/hygiene.py`) and the open work threads (`backend/src/kb/ops/threads.py`), mails the nightly report (`backend/src/kb/ops/nightly_report.py` → `backend/src/kb/maintenance/notify.py`, HTML + text; config `meta/ops/sync.toml` — `mode = "digest"` every night, `"problems"` only when something needs fixing; password in the macOS keychain) and logs the run to `meta/.ops/runs.jsonl`; the dashboard **Ops** tab (`/ops`) shows the same live. See [`meta/automation-daily-sync.md`](automation-daily-sync.md).

## Intent router — casual requests → skills

Map what the user says to a skill before acting; read that skill's `SKILL.md`, then follow it. A casual request **is** the ask: "fix the graph legend" means start the PR flow, not "suggest a fix".

| The user says… | Do | Lands as |
|---|---|---|
| "fix / change / add / improve … the dashboard, explorer, graph, ingest, CLI, a skill, lint" — anything in tooling | `infra-pr`: `ship start <feature> --worktree` → implement → `ship commit "fix\|feat\|chore(<component>): …"` → `ship pr` → `ship merge` (unless held: schema/paradigm or the user asked to review → `pr --hold`, wait for their `approve`) → give the link | PR `… (#N)` |
| "new note type / new field / lint should require …" | `infra-pr` as a **schema** PR: bump `SCHEMA_VERSION`, add `backend/src/kb/migrations/NNNN_*.py`, `ops migrate` on the branch | PR, bumps y |
| "what do I know about … / where did I read … / compare …" | `query-knowledge` (read-only) | nothing |
| "which sources do I have on … / what does this undigested paper say / is it worth digesting / check this source against my notes" | `explore-raw-data` (read-only) | nothing |
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
| "share the KB / export for an LLM" (a zip of the text) | `export-kb` | zip |
| "share / publish the site", "deploy main", "deploy status", "rollback the site", "snapshot the site", "list / remove snapshots", "audit", "time machine" | `share-kb` (Cloudflare; `pixi run share -- …`) | Worker version, `.cache/share/status.json` |
| "create a skill / new workflow" | `create-skill` → `infra-pr` | PR |

**Tooling or knowledge?** The target decides: files under `wiki/`, `raw/`, `think/` are knowledge (ops, straight to main); code, skills, dashboard, docs and config are tooling (PR). When one request touches both, ship the tooling PR first, then do the knowledge step on main. When the target is unclear, ask one short question.

## Page layers

Every wiki page has a `layer:` and a `type:` within it (`backend/src/kb/core/schema.py` `LAYER_OF`). Verbs:
**Add** (scrap into `raw/inbox/`) → **Catalog** (file the raw item, create its Source page at
`depth: listed`) → **Digest** (deepen that same page in place: easy, full, deep).

| Layer | Types | What it is |
|-------|-------|------------|
| **source** | paper, part, lecture, article, video, conversation, ai-chat, blog-post | the digest of one raw item, faithful to it; carries `depth:` |
| **collection** | book, notebook (page partition table) · course, series (Contents table) · aux `scope` | a table grouping sources |
| **concept** | idea, topic, question, person · aux `distilled-think` | knowledge across sources; ends with `## My notes` |

`depth:` (sources only, ordered) — what each depth means, and which depths each source type reaches:

| depth | means |
|-------|-------|
| `listed` | cataloged stub, not read yet |
| `easy` | abstract skim: Problem / Main result only (`easy-digest`, Haiku) |
| `full` | full note with Key equations (`full-digest`) |
| `deep` | thesis-critical: full + neighbor papers, q- stubs, topic threads (`deep-digest`) |

| source type | reaches | usually |
|-------------|---------|---------|
| paper | listed · easy · full · deep | any of the four |
| part | full · deep (created by a scoped book digest) | full |
| lecture | full · deep (created from a course row) | full |
| blog-post | listed · easy · full | easy |
| article | easy · full | easy |
| conversation, ai-chat | easy · full | easy |
| video | easy · full | easy or full |

Retired names (schema 1.0, no read compatibility — lint errors and names the replacement):
`type: theme` → `topic`, `type: concept` → `idea`, `digestion-status` → `depth`, depth `catalog` →
`listed`, disposition `digested` → `source`; "hub" → collection, "MOC" → topic page, "reading
unit" → source.

## Frontmatter

```yaml
type: <type>                 # see Page layers
layer: source|collection|concept   # right after type:, must match the type
status: to-read|reading|digested   # sources + collections; idea/topic: seed|growing|solid;
                             # question: open|partial|resolved; distilled-think: review|applied|archived;
                             # scope: active|parked; person: none — see below
depth: listed|easy|full|deep # sources only — listed ⇒ to-read|reading, easy/full/deep ⇒ digested
area: [info-theory]          # topic slugs only (whitelist TOPIC_SLUGS in backend/src/kb/core/schema.py)
related: [tensor-rank]       # bare slugs — wiki/ is flat, so no paths
aliases: [old-slug]          # renamed pages keep their old slug; `kb.ingest resolve <old-slug>` finds them
raw: raw/printed-docs/y.pdf  # sources + book/notebook (a list for multi-file lectures); `none` + a `url:` if read externally
book_pages: 419              # book/notebook only — total PDF pages
book: <book-slug>            # part only — its collection; plus section: and section_pages: A-B
course: <course-slug>        # lecture — its collection
short: rl                    # course/series — filename prefix of its raw members
institution: runi            # course only, plus course_code:, semester:, lecturer:
```

| Prefix | Type (layer) | Prefix | Type (layer) |
|--------|------|--------|------|
| `paper-` | paper (source) | `book-` | book (collection; long PDF) |
| `part-` | part (source; `part-<book stem>-<topic>`) | `notebook-` | notebook (collection; long handwritten PDF) |
| `lecture-` | lecture (source) | `course-` | course (collection; `course-<institution>-<name>`) |
| `article-` | article (source; web clip, tutorial) | `series-` | series (collection; `series-<author>-<name>`) |
| `blog-` | blog-post (source) | `scope-` | scope (collection, aux) |
| `video-` | video (source) | `theme-` | topic (concept) — exactly the 10 TOPIC_SLUGS |
| `conversation-` | conversation (source; email thread) | `q-` | question (concept) |
| `chat-` | ai-chat (source; LLM chat) | *(bare)* | idea, person (concept) |
| `distilled-think-` | distilled-think (concept, aux) | | |

**`## My notes`** — every concept page (idea, topic, question, person) ends with a reserved
`## My notes` section that is the user's: no tool overwrites it and it stays last
(`backend/src/kb/core/wikiio.py`); lint warns when a page has two or it is not last. Agents never write in it.

**Person pages are handle-driven** (`backend/src/kb/core/persons.py`, schema 0.12). Frontmatter holds only
handles, edges, contact and a date (besides `type: person`, `layer: concept`) — no `status`, `area`, `related` or `affiliation`:

```yaml
url: https://…        # homepage      ⇒ ## Courses
scholar: https://…    # Scholar       ⇒ ## Bibliography, ## Cataloged in vault
github: none          # ⇒ ## Repos            none = checked, there is none (no section)
youtube: unknown      # ⇒ ## Videos & talks   unknown = checked, not found; a missing key = not checked
blog: https://…       # feed          ⇒ ## Writing
wikipedia: https://…  # Wikidata      ⇒ ## Roles & companies, ## Academic lineage
email: …              # contact, no section
orgs: [..] advisors: [..] students: [..]    # bare slugs; [] = checked, nobody
verified: 2026-10-21  # set by finalize; pages without it are the `persons-unverified` backlog
```

Each generated heading carries `<!-- from: <handle|manual> -->` and is rewritten by
`index-researcher finalize` from `meta/.researcher/<slug>/manifest.json`; `## Why it matters
here` (must link a topic or idea), `## Meeting log`, `## My notes` and custom sections are hand-owned and
never touched. Lint enforces the handle ⇒ section rules on verified pages and warns on
non-reciprocal `advisors`/`students`. See `skills/build-researcher-profile/SKILL.md`.

Wikilinks are always bare: `[[tensor-rank]]`, never `[[wiki/tensor-rank]]`. Paths into `raw/` go in backticks, not wikilinks.

## The corpus manifest

`meta/corpus.tsv` has one row per file in `raw/`. Nothing can be silently forgotten.
Columns: `path sha1 kind disposition slug collection` — hand-edit only `disposition` and `collection`.

| disposition | meaning |
|-------------|---------|
| `queued` | keep, not yet written up — **the real backlog** |
| `source` | a Source page (or book/notebook) cites it via `raw:` |
| `partial` | **a book with only some parts digested** — the rest is still backlog |
| `skip` | explicitly not worth a note (a decision, not neglect) |
| `sidecar` | agent-written `parsed.md` inside an email thread folder |
| `dupe:<path>` | superseded by another file |
| `ink:<path>` | reMarkable annotation overlay belonging to `<path>` |
| `asset:<path>` | a figure downloaded with the web clip `<path>` (`raw/images/<clip stem>-NN.<ext>`) — part of the clip, never backlog or a collection member of its own |

The linter maintains it: a new file appears as `queued`; a file gone from disk is removed; **a sha1 change on a `source` file re-opens it as `queued`** — so re-annotating a paper on the tablet automatically re-queues it.

**`collection`** — comma-separated collection or person slugs the file belongs to (`course-runi-rl`,
`book-…`, `series-…`, or a researcher's person page such as `nadav-cohen` for their
bibliography). Lint checks every slug is a collection or person page, and that each course/series
`## Contents` table lists **exactly** the files whose `collection` names it.

## Course and series collections

A `course-` / `series-` page is a collection over member raw files: Overview → Contents → Threads
(`backend/src/kb/core/hubs.py`, `meta/templates/course.md`, `series.md`). Each Contents row is one source —
usually one file, sometimes several (slides + the handwritten notes taken in that lecture):

```
| # | Item | Raw | Status | Note |
|---|------|-----|--------|------|
| 1 | Lecture 1 · Introduction | `raw/presentations/rl-lecture-01-introduction.pdf` | full | [[lecture-rl-01-introduction]] |
| 2 | Lecture 2 · MDPs | `raw/presentations/rl-02.pdf` `raw/handwritten/rl-mdp.pdf` | — | |
| 3 | Course book | `raw/printed-docs/rl-course-book.pdf` | partial | [[book-rl-course-book]] |
```

Row status: `skip` | `—` (backlog) | `partial` (the row is itself a book/notebook collection) | `easy` |
`full` | `deep` (the source's depth). **The table is the truth for member dispositions** — a `—` row is backlog.
A row's identity is its raw paths; `#` is display order. The collection's `status` follows its rows.

## Naming

Every format folder except `emails/` is flat; names are lowercase ASCII kebab, unique across the
vault. Papers and books use **`<year>-<kebab-title>.pdf`** — sortable, greppable, and the year is
metadata you would otherwise have to open the file to find.

```
2023-toolformer.pdf
1948-a-mathematical-theory-of-communication.pdf
```

The linter enforces the pattern and cross-checks the filename year against the digest's `year:` frontmatter, so the two cannot drift apart.

Other members of a course/series are named **`<short>-<topic>.<ext>`**, where `short` is the collection's
`short:` frontmatter (`rl-lecture-01-introduction.pdf`). Email thread folders are
`<YYYY-MM-DD>-<kebab-thread>`. Older origin-named sources keep their prefixes:

| Origin | Pattern | Example |
|---|---|---|
| לא מדויק blog (gadial.net) | `blog-not-exact-<post>` | `blog-not-exact-jordan-form-in-practice.md` |
| Linear Algebra 1 | `linear-algebra-1-<daniel-notes-on-maman\|course-book\|theorem-and-definitions>-<topic>` | `linear-algebra-1-daniel-notes-on-maman-01.pdf` |
| Linear Algebra 2 | `linear-algebra-2-course-book-<part>` | `linear-algebra-2-course-book-part-a.pdf` |

Provenance is kept, not lost: the original name lives in `meta/raw-renames.tsv` (old → new, applied by `backend/src/kb/maintenance/rename_raw.py`, which also carries `corpus.tsv` rows and rewrites wiki references) and, for `.md`, in frontmatter `original_name`/`title`/`aliases`. Raw `.md` files carry filter tags — `source/blog-not-exact`, `source/course-book`, `source/daniel-notes-on-maman`, `source/theorem-and-definitions`, `subject/<x>`, `course/<x>`; PDFs are filtered by filename prefix (`file:linear-algebra-1-`). `backend/src/kb/maintenance/migrate_model.py` flattens every other old-layout file to `<short>-<topic>.<ext>`.

⚠️ reMarkable's `X (annotations).pdf` exports are **ink-only overlays**, not annotated documents — typically a few KB against a multi-MB source, and unreadable on their own. They have all been deleted. If new ones appear, do not delete the source document in their favour.

## Note sections

Sources:
- **paper** — Setup & assumptions → Proof idea (sketch only) → Key equations → Takeaways for my thesis → Connections → Links out (`meta/templates/paper.md`; at `depth: listed` it holds only **Problem:** / **Main result:** lines)
- **part** — as paper, plus a `> Part of [[book]] · pp. A–B` line under the title
- **lecture** — `> Lecture of [[course]]` line → Setup & assumptions → Key equations → Takeaways for my thesis → Connections → Links out
- **article / conversation** — Key claims → Key equations → Takeaways for my thesis → Connections → Links out (conversation = an email thread)
- **ai-chat** — rendered from its `meta/chats/` tree by the chat pipeline (`conversation:` names the tree)
- **blog-post** — rendered by `backend/src/kb/ingest/blog.py`: Blog Post Summary → Key concepts → Post
- **video** — Key ideas → Key equations → Takeaways for my thesis → Connections → Links out

Collections (tables of sources, never sources themselves):
- **book / notebook** — Overview (≥1 paragraph, required) → Partition → Key concepts → Threads
- **course / series** — Overview (≥1 paragraph) → Contents → Threads

Concepts (generated sections first, then `## My notes`, always last):
- **idea** — One-liner → Intuition → Formal → Why it matters → Connections → Open questions → My notes
- **topic** — Scope → Key concepts → Threads → Papers → My notes (research topics only; one per TOPIC_SLUGS entry)
- **question** — Question → Why it matters → What would answer it → Current state → Links → My notes
- **person** — generated handle sections + hand-owned Why it matters here / Meeting log → My notes
- **distilled-think** — Summary (review prose) → Proposed propagation → Not promoting (transient; use `--cleanup` after apply)

Templates for every type: `meta/templates/<type>.md`.

## Topic whitelist (`area:`)

`statistics`, `optimization-theory`, `learning-theory`, `info-theory`, `implicit-regularization`, `tensor-factorization`, `complex-nn`, `quantum`, `boolean-analysis`, `fourier-analysis` (`TOPIC_SLUGS`). Each has exactly one topic page `theme-<slug>` (`type: topic`). Courses are `course-*` collections, not topics.

## Semantic lint

**Structural lint** (`backend/src/kb/lint/lint.py`): links, schema, inbox — unchanged.

**Semantic lint** (`backend/src/kb/core/coherence.py`): meaning-level checks, 0 LLM.

| kind | meaning | action |
|------|---------|--------|
| `internal` | bad ingestion — wiki stale/wrong vs source | **fix** (re-digest / edit); score ≥ 70 → lint ERROR |
| `external` | two digested sources disagree | **note** on each paper's `## Connections` / `## Links out` |
| `cosmetic` | graph hygiene | warn only |

```
python3 -m kb.core.coherence status
python3 -m kb.core.coherence fixed <id>    # internal resolved
python3 -m kb.core.coherence noted <id>    # external recorded on paper
python3 -m kb.core.coherence dismiss <id>
python3 -m kb.search.semfind topic theme-info-theory   # `theme` / `moc` kept as aliases
```

Manifest: `meta/coherence-warnings.tsv` (regenerated on lint; statuses persist).

After full/deep digest or distill apply: `SEMFIND_READY` → `skills/semantic-lint-hop/SKILL.md`. On-demand topic audit: `skills/lint-moc/SKILL.md`.

## Distill think

Human writes in `think/*.md` (schema-free). Distill produces a transient `wiki/distilled-think-*.md` for review, then patches the public KB on apply.

```
python3 -m kb.distill propose <think-file>              # → distilled-think page + plan.json
python3 -m kb.distill revise <think-file>               # re-read think/, keep edited Summary
python3 -m kb.distill apply <think-file> --cleanup       # propagate + delete distilled page
python3 -m kb.distill abort <think-file>
```

`think/` is never agent-edited. See `skills/distill-think/SKILL.md`.

## Skill ladder

Read `skills/README.md` (§ Adding a skill) before any workflow. Run `pixi run lint-skills` then `pixi run sync-skills` after editing skills.

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

**`digest` alone → ask tier (easy / full / deep).** Bare "digest" never triggers `full-digest`.

**Dedup:** always `resolve` before `scrap`. If FOUND → cite `[[slug]]`; don't re-download.

```
python3 -m kb.ingest resolve <url|arxiv|slug> # check vault first (0 LLM)
python3 -m kb.ingest scrap <url>              # → raw/inbox/ (blocked if duplicate)
python3 -m kb.ingest scrap-mail <mbox-or-eml> # → raw/inbox/mail-.../ (thread + attachments)
python3 -m kb.ingest scrap-gdrive --dry-run   # preview a mounted Drive folder pull (0 bytes)
python3 -m kb.ingest scrap-wordpress <site> --prefix <collection short>   # every post of a WordPress.com blog + figures → inbox
python3 -m kb.ingest catalog <inbox-path>     # → raw/<format>/ (+ paper- Source page at depth listed, papers only)
python3 -m kb.ingest catalog <inbox-path> --collection <collection|person> [--format <folder>] [--title T]
python3 -m kb.ingest easy-digest <slug|raw>   # depth easy: abstract skim (ticks a collection row if a member)
python3 -m kb.ingest easy-digest <raw> --into <page> [--no-tick --no-lint]   # series page / batch mode
python3 -m kb.ingest full-digest <raw>        # medium: begin→finalize
python3 -m kb.ingest full-digest <collection-slug> --row N   # one course/series Contents row
python3 -m kb.ingest easy-spotcheck pick <slug...>      # ~5% of easy digests for a Sonnet re-read
python3 -m kb.ingest easy-spotcheck log <slug> --model <m> --verdict ok|fix [--note ...]
python3 -m kb.ingest deep-digest <raw> --confirm-heavy
python3 -m kb.ingest toc <raw>                # book partition (or a proposed one) (0 LLM)
python3 -m kb.ingest refetch-raw [--apply]    # replace paper PDFs stamped with another arXiv id than their page cites (0 LLM)
```

**scrap-wordpress** pulls a whole WordPress.com blog through its public API (0 LLM): one Markdown clip per
post with every formula restored losslessly from the LaTeX image URLs, embedded players as links, and the
figures downloaded next to it as `<clip stem>-NN.<ext>` (original URL kept as the link title; a figure that
cannot be fetched stays a remote link). `--since`/`--limit` resume or trial a pull; dedup is by post URL.
Then `drain-inbox --collection <series-slug>`: clips become `raw/web-clips/` members of the series, their
figures `raw/images/` rows bound as `asset:<clip>` (lint derives this from the names), one lint at the end.

**arXiv is never guessed.** The metadata client (`backend/src/kb/ingest/arxiv_meta.py`) spaces calls 3 s apart
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

**Digesting a collection row:** `full-digest|deep-digest <collection-slug> --row N`. The page type follows the
format: `presentations/`, `handwritten/` → `lecture-`; `emails/` → `conversation-`; `web-clips/`
or non-PDF `printed-docs/` → `article-`; `printed-docs/` PDF → `paper-`. LLM chats become `chat-`
pages through the chat pipeline instead. `finalize` ticks the row; `easy-digest` ticks it too and
sets `status: digested`. A raw path that is a collection member auto-scopes to its row.

**Books are a collection plus parts.** A PDF of ≥60 pages is a book. It gets one `type: book` page
(slug `book-<PDF stem>`; a long handwritten PDF is a `notebook-<stem>`) holding an `## Overview` paragraph and a `## Partition` table that splits
pages `1..book_pages` into **disjoint, exhaustive parts** — a part can be a chapter, merged short
chapters or half a long one; front/back matter rows are `skip`. Each digested part is its own
`type: part` page (slug `part-<book stem>-<topic>`); undigested parts are table rows, not pages.

```
| # | Part | Pages | Status | Note |
|---|------|-------|--------|------|
| 1 | Front matter · Prefaces | 1–18 | skip | |
| 2 | Chapter 1. Boolean functions and the Fourier expansion | 19–42 | full | [[part-2014-analysis-of-boolean-functions-ch1-fourier-expansion]] |
| 3 | Chapter 2. Basic concepts and social choice | 43–68 | — | |
```

Digesting a book is always scoped — the CLI prints the partition and exits 2 instead of guessing:

```
python3 -m kb.ingest toc <raw>                     # partition [x]/[ ]/[-]; --depth 2 adds the outline
python3 -m kb.ingest full-digest <raw> --part 3    # a row of the partition
python3 -m kb.ingest full-digest <raw> --pages 43-55  # carves a new part out of undigested rows
python3 -m kb.ingest full-digest <raw> --section 2 # an outline entry (chapter number, #index, text)
python3 -m kb.ingest full-digest <raw> --whole-book  # override the gate (writes a paper)
```

The first scoped digest creates the book page from `meta/templates/book.md` with a partition
proposed from the PDF outline (split only at chapter/section boundaries, ≤60 pp per part); write
its Overview by hand. `finalize` writes the `type: part` page and ticks its row. A part's identity
is its page range — the `#` column is display order and renumbers when a row is split.

**The partition is the truth** (`backend/src/kb/core/books.py`, checked by lint): gaps or overlaps are errors,
a part over 60 pages is a warning, a digested row must link its part page and match its
`depth`, and the part's `book:`/`raw:`/`section_pages:` must agree with its row.
Coverage = digested pages ÷ non-skip pages; below 100% the raw file is `partial` in
`meta/corpus.tsv` — never `source` — warns on every run and counts in `--health` as
`partial-books`. The book's `status` follows coverage. Re-digesting a finished part is refused.

During `full-digest` / `deep-digest`, `backend/src/kb/git/guard.py` blocks direct writes to session-owned wiki paths — use `draft` + `finalize`. Legacy `reingest-*` is bootstrap-only.

**Triage:** anything in `raw/inbox/` gets cataloged or deleted. The inbox is a queue, not storage.

**Query:** Karpathy Query operation — read wiki, cite `[[slugs]]`, file good answers back on request. See `skills/query-knowledge/SKILL.md`. Raw sources are reached only through `explore-raw-data` (`python3 -m kb.search.explore_raw find|read|check|recommend`, cataloged files only, 0 LLM): `skills/explore-raw-data/SKILL.md`.

```
python3 -m kb.search.query candidates "<keywords>"   # rank slugs (0 LLM)
python3 -m kb.search.query mocs                      # topic pages (theme-*) as entry points
```

Workflow: `index.md` → `candidates` → read 3–8 pages → synthesize. Not the same as `kb.ingest resolve` (ingest dedup).

## Migration

The schema 1.0 source model was applied by `backend/src/kb/migrations/0008_source_model.py` (front matter
and `corpus.tsv` only, bodies byte-identical; site inventory in `meta/migration/source-model/`).
Earlier, `python3 -m kb.maintenance.migrate_model` (dry run → `meta/.migrate/plan.json`) / `--apply` moves an
old-layout vault to this model: old raw folders → format folders, `collection` filled from
`meta/migration/collections.tsv`, slugs prefixed, old topic slugs → `theme-`, old per-course index pages
merged into `course-`/`series-` collections, stub chat/mail pages quarantined to
`_quarantine/migration-<stamp>/`. `--apply` refuses while `collections.tsv` has `TODO` cells or
ingest sessions are open; `--rewrite-think` opts in to rewriting links inside `think/`. Idempotent.
