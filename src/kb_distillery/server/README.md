# kb_distillery.server — the typed HTTP API

`python -m kb_distillery.server --port 8765` (`pixi run app`) serves, on one loopback port:

- the typed API (`/api/...`, OpenAPI at `/openapi.json`, docs at `/docs`),
- the React shell from `src/kb_distillery/_webapp` under `/app` (SPA fallback); `src/kb_distillery/_webapp` is gitignored build
  output that the server rebuilds from source on start when the sources changed (`--no-build` skips it),
- the old dashboard page URLs (`/start`, `/`, `/ops`, `/covector-visualization.html`, ...) as redirects to their React
  routes (`PORTED` in `app.py`); other unowned paths are a 404.

Vocabulary in models, routes and docs is the data model's: `layer: source|collection|concept`, `type`,
`depth: listed|easy|full|deep`.

## Add a router in 5 lines

1. `src/kb_distillery/server/models/<resource>.py` — pydantic models (`from kb_distillery.server.models.base import ApiModel`).
2. `src/kb_distillery/server/routers/<resource>.py` — `router = APIRouter(tags=["<resource>"])` plus the routes;
   each route is thin over a `kb_distillery.services.*` function and declares `response_model=`.
3. `tests/server/test_<resource>.py` — `TestClient(create_app())`, assert the model validates.
4. `pixi run api-schema` — regenerates `web/src/api/schema.d.ts`; commit it.
5. Done. `create_app()` includes every module in `routers/` that exposes `router`; **never edit `app.py`**
   (and no shared file at all: the Origin/Host/body guards are app-wide).

## Conventions

- One model module and one router module per resource; modules starting with `_` are not routers.
- Models extend `ApiModel` (`extra="allow"`): a typed route returns the same JSON as the legacy endpoint it
  replaces. List the fields the frontend uses; tighten the model when the legacy page is deleted.
- JSON keys must be strings; a field named like a `BaseModel` attribute (`schema`) gets `Field(alias=...)`.
- Reads are free. A mutating route (POST/PUT/PATCH/DELETE) needs a loopback `Origin` header (browsers send
  it; `curl -H 'Origin: http://127.0.0.1:8765'`). Body cap 4 MB. Host must be loopback.
- Raw files: take `full: str = Depends(safe_raw_path)` from `kb_distillery.server.security` (route param named `path`);
  it 404s on traversal, symlink escape, `raw/inbox/` and missing files.
- Streams: `return sse_response(generator_of_(event, data))` from `kb_distillery.server.sse`. Frames are
  `event: <name>\ndata: <json>\n\n`; `("ping", None)` and quiet stretches emit `: ping`; a client
  disconnect closes the generator (so an agent behind it stops).
- Services stay HTTP-free: put the logic in `kb_distillery.services.<x>`, the router only adapts.

## Files

`app.py` create_app + discovery · `security.py` guards · `sse.py` SSE helper · `assets.py` static dir, viz reporter, PDF thumbnails ·
`spa.py` /app · `export_schema.py` OpenAPI -> TypeScript (`pixi run api-schema`, `api-schema-check`) ·
`models/` · `routers/`.
