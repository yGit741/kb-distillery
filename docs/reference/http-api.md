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
| `GET /api/sessions` | Saved chat sessions, newest first. |
| `GET /api/sessions/{id}` | One saved chat session with its messages. |
| `PUT /api/sessions/{id}` | Create or replace a chat session. |
| `PATCH /api/sessions/{id}` | Rename a chat session. |
| `DELETE /api/sessions/{id}` | Delete a chat session. |

The model names in the schema use the data model's words: `layer` is `source`, `collection` or `concept`, and `depth` is `listed`, `easy`, `full` or `deep`.

## Chat sessions

Past chats have one home on the machine that runs the server: one file per chat, `<kb>/.local/sessions/<id>.json`. They are never committed: the first write puts a `.gitignore` of `*` inside `.local/` and, when the knowledge base is a repository, adds `.local/` to its local exclude file.

A session is `{id, title, created, updated, model, effort, backend, messages, usage}`. `messages` is stored as the chat screen keeps it and is never interpreted. `usage` is computed on save: `turns` is the number of questions and `cost_usd` the sum of the answers' billed cost (subscription turns add nothing).

- `id` is lowercase letters, digits, dashes and underscores, at most 64 characters (the chat screen uses its chat id without the `kb-chat:` prefix).
- `GET /api/sessions` returns `{sessions: [{id, title, created, updated, turns, cost_usd, preview, model, effort, backend}]}`, newest `updated` first. `preview` is the first line of the first question. A damaged file is left out of the list.
- `PUT /api/sessions/{id}` takes `{messages, title?, created?, model?, effort?, backend?}` and replaces the whole document. A new session takes `created` from the body or now, and its title from the first question; an existing one keeps its `created` and its title unless a `title` is sent, so a rename survives the next save. `updated` is set by the server. A document over 4 MB is refused.
- `PATCH /api/sessions/{id}` takes `{title}`. `DELETE /api/sessions/{id}` removes the file.
- Errors are `{"error": "..."}`: 400 for a bad id, title or body, 404 for an unknown session, 409 when the file of a session you read or rename is damaged (a `PUT` replaces it), 500 when the file cannot be written. On a server started with `KB_READ_ONLY=1` every write is **405**; the two reads still work.

The chat screen uses these when the `agent-mode` flag is on: it saves the chat after each finished turn, copies the chat its browser tab holds once on first load, and lists past chats in the session panel. With the flag off the chat stays in the browser tab, as before.

## Add an endpoint

Add a model in `src/kb_distillery/server/models/`, a router in `src/kb_distillery/server/routers/`, a test in `tests/server/`, and run `pixi run api-schema`. The app includes every router module automatically. See `src/kb_distillery/server/README.md`.
