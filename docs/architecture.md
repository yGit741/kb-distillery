# Architecture

This page names the parts, shows how data moves, says where code lives, and lists the rules that do not change. It describes the code on `main`.

## The parts

| Part | What it is | Where |
|---|---|---|
| Engine | The code: linter, ingest and digest pipelines, versioned knowledge operations, graph and search, the API and the app. It knows nothing about a topic. | this repository |
| Knowledge base | A folder with `kb.toml`, `raw/`, `wiki/` and `meta/`. It holds knowledge and its own settings. It is its own git repository. | `~/knowledge/<id>`, or any folder passed with `--kb <path>` |
| Kit | The schema a knowledge base follows: page types, relations, fields, filename prefixes. Versioned. | `src/kb_distillery/kits/<name>/kit.toml` |
| Storage connector | How raw sources are reached. Built in: local folder and Google Drive mount. Others register as packages. | `src/kb_distillery/storage/` |
| Publisher | Puts a snapshot of a knowledge base on a host. Optional. Cloudflare is built in. | `src/kb_distillery/publish/` |
| Think | One personal journal outside every knowledge base. | `~/knowledge/think/` |
| LLM gateway | The only code that calls a model. | `src/kb_distillery/llm/` |

## How the parts connect

```mermaid
flowchart LR
  subgraph engine[Engine]
    lint[lint: the schema]
    ops[ops: kb commits]
    llm[llm gateway]
    pipe[ingest and digest]
    graph[graph and search]
    api[API and app]
  end
  kit[Kit] -->|schema| lint
  pipe --> llm
  kb[("Knowledge base: raw, wiki, meta")] <--> ops
  kb --> graph --> api
  conn[Storage connector] --> kb
  src[Folder, Drive mount, package store] --> conn
  think[("Think")] -->|distill send| kb
  api -.->|optional| pub[Publisher]
```

## Data flow

```
raw/inbox -> catalog -> raw/<format>/ + meta/corpus.tsv -> digest -> wiki/ -> lint -> graph -> app
  scrap     (no model)    (immutable inputs)                easy/full/deep  (linked)   (index)   (API and React)
```

1. `scrap` puts a file or URL into `raw/inbox/`. `catalog` moves it to `raw/<format>/` and records it in `meta/corpus.tsv`. Neither calls a model.
2. A digest deepens a source page in `wiki/` in one of three tiers. It runs as a transactional session that reads `raw/` and writes `wiki/`.
3. `distill lint` checks every page against the schema of the knowledge base and regenerates `wiki/index.md`, the `wiki/<type>/index.md` section indexes and `meta/corpus.tsv`.
4. The graph is built from the links between pages and from the typed `relations:` that pages state.
5. The app is a FastAPI server plus a React app in `web/`. `distill launch` starts both.
6. Every knowledge operation is one commit on the `main` branch of the knowledge base: `kb(<op>): <summary> (kb-x.y.z)`. Undo, snapshots and the time machine read that history and its tags.

`wiki/` is the root of the Open Knowledge Format bundle. It holds `index.md` and `log.md`, and pages link to each other with relative `slug.md` links.

## Where code lives

| Path | Holds |
|---|---|
| `src/kb_distillery/cli/` | The `distill` command table, help and dispatch. `legacy.py` is the old `kbd` name. |
| `config/` | Finding and selecting a knowledge base (`kb.py`), vault paths (`paths.py`), the kit loader (`kit.py`), the user config folder (`userdir.py`), feature flags (`flags/`). Depends on nothing else in the engine. |
| `vault/`, `lint/` | Schema, page model, graph helpers, the linter. |
| `ingest/`, `distill/`, `digest/`, `parse/` | Pipelines over sources and think notes. Source connectors live in `ingest/sources/`. |
| `graph/`, `search/` | Relations, proposals, the graph snapshot, search. |
| `llm/` | The LLM gateway and the prompts (`llm/prompts/`). |
| `ops/`, `git/` | Versioned knowledge operations, nightly sync, reports; hooks, guards, commit policy. `git/ship.py` is the pull request tool for engine changes. |
| `storage/`, `hosting/` | The storage connector interface and registry; the publisher interface and registry. |
| `publish/` | `publish/site/` builds the site, `publish/cloudflare/` is the Cloudflare publisher with its Worker, `publish/export.py` writes the export. |
| `services/`, `server/` | Domain services and the FastAPI routers (`python -m kb_distillery.server`). |
| `kits/` | The kits: `kit.toml`, defaults, skills, hooks. |
| `migrations/` | Schema migrations, one file each. |
| `web/` | The React app (Vite, TypeScript). |
| `tests/` | pytest, mirroring the package; `tests/e2e/` holds a browser test of the graph screen (`pixi run test-e2e`; it skips without Playwright). |
| `examples/demo/` | The tracked sample knowledge base. |
| `examples/launchd/` | Templates for the nightly job. |
| `scripts/` | Launch script and git hooks. |
| `.claude/` | The maintainer's local agent tooling. It is not shipped in releases and you do not need it. |

## Rules that do not change

- The linter is the schema. If `distill lint` passes, a write is legal.
- `raw/` is immutable. A write guard refuses writes there, and a connector refuses to replace a key.
- One transactional workflow (ingest, ops or distill session) runs at a time.
- Every model call goes through `kb_distillery.llm`. A test fails on any other call. See [ADR 0001](adr/0001-single-llm-gateway.md).
- Knowledge never enters this repository. Only `examples/demo` is tracked. See [ADR 0003](adr/0003-knowledge-outside-the-repo.md).
- A knowledge base extends its kit and never edits it. See [ADR 0002](adr/0002-kits-over-templates.md).
- The core does not import a publisher. It asks a registry.
- Engine changes go through pull requests. Knowledge commits itself per operation.
- A feature that cannot land in one pull request ships behind a flag in `src/kb_distillery/kits/base/defaults/flags.toml`.

## Layers

`pyproject.toml` declares the allowed imports between packages, and `pixi run lint-imports` enforces them. From the top:

1. `cli`, `server`, `doctor`, `init_kb`: entry points.
2. `services`, `publish`, `webbuild`: use cases and what ships the result.
3. `ingest`, `digest`, `distill`, `graph`, `search`, `lint`, `metrics`, `ops`, `git`, `migrations`, `parse`: pipeline stages.
4. `vault`, `llm`, `storage`, `hosting`: the vault model, the gateway, connectors and the publisher port.
5. `config`: locations and settings.

A package imports only from the layers below it. One cycle (`graph/propose.py` and `services`) is listed as an ignored import until it is removed.

## Not done yet

- Some modules still read `raw/` directly instead of through the connector. `tests/storage/raw_access_baseline.txt` lists them, and the list only shrinks.

See the [roadmap](public-roadmap.md).
