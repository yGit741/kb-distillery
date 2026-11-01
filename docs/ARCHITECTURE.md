# Architecture

kb-distillery turns sources you collect (papers, slides, mail, web clips) into a linked, linted wiki you can read, search and query, with an agent doing the synthesis and a linter keeping it honest. This page is the map: what the parts are, how data flows, where code lives, and the rules that do not bend. It describes what the code does today; parts still being built are marked **planned** or **in progress**.

## The parts

| Part | What it is | Where |
|---|---|---|
| **Engine** | The code: linter, ingest and digest pipelines, ops (versioned knowledge commits), graph and search, the API and the app. Knows nothing about any one topic. | this repo |
| **Knowledge base (kb)** | A folder with `kb.toml`, `raw/`, `wiki/`, `meta/`. Holds only knowledge and its settings. Each kb is its own git repository. | `kbs/<id>`, or any folder given as `--kb <path>` |
| **Kit** | The schema a kb follows: page types, typed edges, fields, filename prefixes. Versioned. A kb names one and may extend it, never edit it. | `src/kb_distillery/kits/<name>/kit.toml` |
| **Storage connector** | How raw sources are reached: list, get, put, info, local copy, auth. Built in: local folder (default) and Google Drive. Third parties register more through the `kb_distillery.storage.connectors` entry-point group. | `src/kb_distillery/storage/` |
| **Publisher** | Sharing a kb as a site, as a plugin outside core. With none configured core runs unchanged. The Cloudflare publisher is the first (code in `src/kb_distillery/share/` and `share/`). Third parties use the `kb.publishers` entry-point group. | `src/kb_distillery/publish/` |
| **Think** | One human-owned, schema-free journal outside every kb. `kbd distill <note> --to a,b` sends a note into chosen kbs with provenance on both sides. Agents never edit it. | `<kbs dir>/think` (its own repo) |

Guides for the three extension points: [kits](../src/kb_distillery/kits/base/defaults/docs/kits.md), [storage](../src/kb_distillery/kits/base/defaults/docs/storage.md), [publish](../src/kb_distillery/kits/base/defaults/docs/publish.md); think in [think](../src/kb_distillery/kits/base/defaults/docs/think.md).

```
                         engine (this repo)
   +-----------------------------------------------------------+
   |  lint (the schema)   ops (kb commits)   kb_distillery.llm   kbd CLI  |
   |  ingest/digest       graph + search     API + app          |
   +--------+-------------------+----------------------+-------+
            | reads             | reads/writes         | optional
     kit (schema)          kb  (kbs/<id>, own git)   publisher (site)
                                |   raw/  wiki/  meta/
                                |
                         storage connector --> raw sources (folder, Drive, ...)

   think/ (own repo, human) --kbd distill--> wiki/distilled-think-*.md in each target kb
```

## Data flow

```
 raw/inbox -> catalog -> raw/<format>/ + meta/corpus.tsv -> digest -> wiki/ -> lint -> graph -> app
   scrap      (no LLM)       (immutable inputs)           easy/full/deep  (linked)  (index)   (API+React)
```

1. **Scrap and catalog** put a file or URL into `raw/inbox/`, then move it into `raw/<format>/` and record it in `meta/corpus.tsv`. No LLM.
2. **Digest** deepens a source page in `wiki/` in three tiers (easy, full, deep) through an agent skill and a transactional ingest session. The digest reads raw, writes only wiki.
3. **Lint** (`kbd lint`) checks every page against the kb's schema and regenerates `index.md` and `meta/corpus.tsv`.
4. **Graph** is built from the wiki links and the typed `relations:` that pages state (`src/kb_distillery/core/graph.py`, `src/kb_distillery/services/graph.py`, `src/kb_distillery/graph/relations.py`).
5. **App**: `kbd app` serves a FastAPI backend plus the React shell in `web/`. Screens not yet ported are still served by the older HTML dashboard (`src/kb_distillery/dashboard/`) behind the API.
6. Every knowledge operation lands as one commit `kb(<op>): ... (kb-x.y.z)` in the kb's own repository, which gives undo, snapshots and a time machine from its history and tags (`src/kb_distillery/ops/`).

## Where code lives

| Path | Holds |
|---|---|
| `src/kb_distillery/` | the Python package `kb`; `cli.py` is `kbd`, `kbconfig.py` finds and selects a kb, `paths.py` is the one vault-root resolver |
| `core/`, `lint/` | schema, kit merge (vault/kit.py), page types, graph helpers; the linter |
| `ingest/`, `distill/`, `search/`, `graph/` | pipelines and queries over the wiki |
| `ops/`, `git/` | versioned knowledge commits; write guards, commit policy, the `ship` PR tool |
| `llm/` | `kb_distillery.llm`, the only door to a model |
| `storage/`, `publish/` | connector and publisher interfaces, registries and built-ins |
| `services/`, `api/` | data services and the FastAPI routers (auto-discovered), typed client for the frontend |
| `share/` | the Cloudflare publisher's code, reached only through `publish/` (core never imports it; off unless a kb or the engine config selects it) |
| `tests/` | pytest, mirroring the package layout |
| `web/` | the React app (Vite, TypeScript) |
| `src/kb_distillery/kits/` | the kits (`base`, `research`): `kit.toml` each; `base/defaults/` holds the flags, routed docs, page skeletons and digest defaults |
| `kbs/` | kbs; gitignored except `examples/demo`, the public sample used by tests |
| `src/kb_distillery/kits/base/defaults/` | defaults for every kb: docs, flags, templates; a kb's `meta/` overrides them |
| `src/kb_distillery/kits/<kit>/skills/` | the workflow skills a kb is given (`base`, `research`); `.claude/skills/` holds the engine's own dev skills |
| `share/`, `scripts/` | the Worker for the Cloudflare publisher; launch script and git hooks |

## Invariants

- **The linter is the schema.** If `kbd lint` passes, a write is legal. Prose rules summarize it; they do not replace it (`src/kb_distillery/lint/lint.py`).
- **`raw/` is immutable.** Agents never write there; the write guard refuses it (`src/kb_distillery/git/guard.py`), and the storage connector refuses to overwrite an existing key. Raw access is moving behind the connector; `tests/storage/raw_access_baseline.txt` lists the modules that still touch `raw/` directly, and it only shrinks.
- **One transactional workflow at a time.** An ingest, ops or distill session holds a lock; a second one is refused until the first commits or aborts.
- **Every LLM call goes through `kb_distillery.llm`.** One `--backend subscription|api|batch` choice (`$KB_LLM_BACKEND`, default subscription); a test fails on any other `claude -p`, SDK or HTTP call. The LLM is optional for browsing and linting.
- **Knowledge never enters this repo.** Only `examples/demo` is tracked; `python -m kb_distillery.lint.privacy` and a secret scan guard the rest.
- **Tooling goes through pull requests** (`ship`); knowledge commits itself per operation on the kb's main.

## Not built yet

`kbd init` and `kbd doctor` exist (see the README quick start). What is still open: moving the remaining `raw/` access onto connectors (a short list of modules is allowed to read `raw/` directly, see [`docs/phase-3-report.md`](phase-3-report.md)), greying out AI features in the app until a login or key exists, and publishing the repository. The roadmap, phase by phase, is [`docs/ROADMAP.md`](ROADMAP.md).
