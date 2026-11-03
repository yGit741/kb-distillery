# HTTP API

The app talks to a typed HTTP API. It is served by `python -m kb_distillery.server --port 8765`, which `distill launch` starts.

| What | Where |
|---|---|
| API | `/api/...` |
| OpenAPI schema | `/openapi.json` |
| Interactive docs | `/docs` |
| React app | `/app` |

The server listens on loopback only. A request must carry a loopback `Host` header. A request that changes data (POST, PUT, PATCH, DELETE) must also carry a loopback `Origin` header. Browsers send it. With curl, add `-H 'Origin: http://127.0.0.1:8765'`. The body limit is 4 MB.

The API follows the knowledge base the server was started with.

## Get the schema

```bash
pixi run python -c "from kb_distillery.server.app import create_app; import json; print(json.dumps(create_app().openapi(), indent=2))" > openapi.json
```

`pixi run api-schema` writes the TypeScript types for the app from the same schema. `pixi run api-schema-check` fails when the committed file is stale.

## Endpoints

This table is generated from the schema on `main`.

| Method and path | Does |
|---|---|
| `GET /api/kb` | The active knowledge base: `kb.toml`, folder, git, types. |
| `GET /api/kb/list` | Knowledge bases the app can load. |
| `GET /api/pages` | Every page as a card, plus links and wanted pages. |
| `GET /api/pages/{slug}` | One page: markdown, backlinks, suggestions. |
| `GET /api/path` | Shortest undirected link paths between two pages. |
| `GET /api/search` | Full-text search over the pages. |
| `GET /api/assets/vault` | An image a page embeds, resolved under `raw/`. |
| `GET /api/assets/chat` | An extracted chat visualization. |
| `GET /api/graph` | The wiki link graph. |
| `POST /api/graph/cypher` | Run a read-only Cypher query (supported subset). |
| `POST /api/graph/shape` | Turn free text into a graph view: Cypher selection plus a style clause. |
| `GET /api/graph/queries` | Named graph queries. |
| `POST /api/graph/queries/{name}` | Run a named graph query. |
| `GET /api/citations` | Citation graph among cataloged papers. |
| `GET /api/relations/proposals` | Relation proposals in a confidence range, best first. |
| `GET /api/corpus` | Raw files of one format with digest columns. |
| `GET /api/raw/{path}` | Manifest facts and a text excerpt. |
| `GET /api/raw/{path}/card` | One raw file as a Home pipeline card. |
| `POST /api/raw/{path}/digest` | Run an easy digest on one raw file. |
| `GET /api/raw/{path}/file` | The raw file itself, read-only. |
| `GET /api/raw/{path}/thumb` | Page-1 image of a raw PDF. |
| `GET /api/videos/{path}` | One video bundle as structured data. |
| `GET /api/scopes` | All scopes with coverage. |
| `POST /api/scopes` | Create or update a scope. |
| `GET /api/scopes/{slug}` | One scope: rows and projection. |
| `DELETE /api/scopes/{slug}` | Delete a scope. |
| `POST /api/scopes/{slug}/duplicate` | Copy a scope under a new slug. |
| `POST /api/scopes/resolve` | Graph node ids to raw files. |
| `GET /api/health` | Health snapshot of the knowledge base. |
| `GET /api/pipeline` | Ingestion and digestion snapshot. |
| `GET /api/ops` | Operations snapshot. |
| `GET /api/lifecycle` | Git lifecycle snapshot. |
| `GET /api/think` | Top-level think notes, newest first. |
| `GET /api/think/{name}` | One think note. |
| `PUT /api/think/{name}` | Save a think note. Uses an optimistic lock on `base_mtime`. |
| `POST /api/think/capture` | Append a quick thought to the inbox note. |
| `GET /api/share/status` | Last deploy of the private site. |
| `GET /api/flags` | The flag registry and each flag's value. |
| `PUT /api/flags/{name}` | Set or clear a runtime flag override. Needs the owner token. |
| `GET /api/backlog` | Backlog items with plan status. |
| `POST /api/chat` | Ask the chat. The reply is a server-sent event stream. |
| `GET /api/chat/status` | Backend, auth, keys (hints only) and spend. |
| `GET /api/chat/settings`, `POST /api/chat/settings` | Read and update chat settings. |
| `GET /api/chat/prompts` | Prompt presets. |
| `GET /api/chat/keys`, `POST /api/chat/keys`, `DELETE /api/chat/keys/{name}` | List, store and remove keys. Only hints are returned. `POST /api/chat/keys/remove` is the older form of the delete. |
| `POST /api/chat/saved` | Save a chat to `raw/inbox/`. |

The model names in the schema use the data model's words: `layer` is `source`, `collection` or `concept`, and `depth` is `listed`, `easy`, `full` or `deep`.

## Graph views from free text

`POST /api/graph/shape` turns a request such as `show papers that mention tensor rank, group by source, colour by type` into a view: Cypher that selects the nodes, plus a style clause that says how to draw them.

```bash
curl -s -H 'Origin: http://127.0.0.1:8765' -H 'content-type: application/json' \
  -d '{"text": "papers that mention tensor rank; group by layer; colour by type"}' \
  http://127.0.0.1:8765/api/graph/shape
```

Request: `text` (up to 4000 characters), `limit` (1 to 500, default 500), `backend` (`subscription`, `api` or `batch`; optional).

Response: `cypher` (a string, or `null`), `style` (the typed spec), `style_text` (the same style as a clause list), `explanation`, `source` (`cypher` or `llm`), `warnings`, and the selection's table (`columns`, `rows`, `row_count`, `truncated`; the first columns are node slugs), plus `backend` and `usd` when a model was asked.

What the text can be:

| Text | What happens |
|---|---|
| Starts with `MATCH` (any case) | Raw Cypher, run as written. A style clause may follow a line that starts with `--` or `style:`. No LLM. |
| A style clause list only | `cypher` is `null`, `rows` is empty: keep the current node set. No LLM. |
| Anything else | One call through `kb_distillery.llm`. The prompt carries the Cypher subset, this knowledge base's node labels and edge kinds, the style grammar and a few examples. The reply is run once to check it. When the Cypher or the style is rejected, the error goes back to the model once. |

The style clauses are separated by `;` or a new line:

| Clause | Takes |
|---|---|
| `group by` | a node property (`type`, `layer`, `depth`, `maturity`, `areas`, `year`, `title`, `slug`, `path`), `label` or `edge-kind` |
| `colour by` (or `color by`) | a node property, `label` or `degree` |
| `size by` | `degree` or a node property |
| `layout` | `force`, `radial`, `grid` or `timeline` |
| `hide` | a node label (`hide Paper`) or an edge kind (`hide MENTIONS`, all caps). `hide label x` and `hide edge x` say which when the spelling is ambiguous. Repeatable, or comma separated. |
| `label` | the node property shown as the node's text |

A later clause of the same kind replaces an earlier one. The same grammar is in `kb_distillery.graph.shape`; `python3 -m kb_distillery.search.cypher shape "<text>"` prints the response as JSON.

Statuses: `422` when the text cannot become a valid view (the unknown clause or the Cypher engine's hint is in `detail`; an LLM answer gets one retry before this), `400` for an unknown `backend`, `502` when the backend failed (no login, no key).

The model is `haiku`. The backend is `subscription` unless `backend` or `$KB_LLM_BACKEND` says otherwise. With `batch` the request waits up to five minutes for the batch to end and answers `502` if it has not, because a page waits on this call; for bulk work use the `api` or `subscription` backend.

## Add an endpoint

Add a model in `src/kb_distillery/server/models/`, a router in `src/kb_distillery/server/routers/`, a test in `tests/server/`, and run `pixi run api-schema`. The app includes every router module automatically. See `src/kb_distillery/server/README.md`.
