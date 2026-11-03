---
name: backend-api
description: >-
  Backend work in src/kb_distillery: add or change a FastAPI router, model or service under kb_distillery.server / kb_distillery.services,
  regenerate the typed frontend client, write pytest tests. Use whenever the user wants a new or changed endpoint,
  route, API, SSE stream or backend test, even if they only say "expose X over HTTP". Use for add an endpoint,
  new router, api-schema. Do NOT use for React screens (app-ui), wiki/raw/think edits, or the removed legacy dashboard pages.
audience: dev
mode: write
---

# backend-api

**LLM tier:** none · **Budget:** 0 tokens

Python package `kb_distillery` under `src/` (src layout). The typed HTTP API is `src/kb_distillery/server`; the logic behind it lives in `kb_distillery.services`. This is tooling: it ships through an `infra/<feature>` PR (`infra-pr`), never on main. Read `src/kb_distillery/server/README.md` first; it is the source of truth for conventions, this skill is the workflow around it.

## Triggers

- `add an endpoint`, `new router`, `change the API`, `expose … over HTTP`, `api-schema`, `backend test`, `backend-api`

## Do NOT

- Build or style a screen in `web/` (use `app-ui`); only regenerate its `schema.d.ts` here
- Hand-edit vault content (that is `wiki-edit` and the writer CLIs)
- Edit `kb_distillery/server/app.py` or any shared file to register a router: discovery is automatic
- Use `sys.path.insert` or hard-code a vault path; take every path from `kb_distillery.config.paths`
- Run git writes directly (go through `infra-pr`)
- Import `kb` with a bare `python`/`python3` inside the repo env: use `pixi run python …` (e.g. `pixi run python -c "from kb_distillery.server.app import create_app"`)

## CLI

```bash
pixi run ship -- start <feature> --worktree
pixi run app
pixi run api-schema
pixi run api-schema-check
pixi run test
pixi run lint
```

## Agent steps

1. **Start the lane.** Run `infra-pr` (`ship start`) before the first edit; the endpoint is a `feat(api): …` or `fix(api): …` commit.
2. **Look at a neighbour.** Copy the shape of `routers/health.py` + `models/health.py` (thin route over a service, typed) rather than inventing one. Streams: `routers/chat.py`; raw files: `kb_distillery.server.security.safe_raw_path`.
3. **Put logic in `kb_distillery.services.<x>`.** Services are HTTP-free and importable from CLI and tests; the router only adapts. Why: the CLI and the API share these functions, and a service is testable without a client.
4. **Model** in `kb_distillery/server/models/<resource>.py`, extending `ApiModel` (`extra="allow"`, so a typed route returns what the legacy endpoint did). List the fields the frontend uses. JSON keys are strings; a field named like a `BaseModel` attribute (`schema`) gets `Field(alias=...)`. Use the data model's words: `layer`, `type`, `depth`.
5. **Router** in `kb_distillery/server/routers/<resource>.py`: `router = APIRouter(tags=["<resource>"])`, each route with `response_model=` and a `summary=`. One model module and one router module per resource; a file starting with `_` is not a router. A typed route wins over the legacy catch-all for the same path.
6. **Mutations** (POST/PUT/PATCH/DELETE) need a loopback `Origin` header; body cap is 4 MB. A route that changes vault content must go through a writer CLI or `ops begin`/`ops commit` so it lands as one op commit.
7. **Test** in `tests/server/test_<resource>.py` (tests mirror the package: `tests/services`, `tests/vault`, …). Use `TestClient(create_app())` and assert the response validates against the model. For writes, build a temp git vault in `tmp_path` and patch the service's root (copy the `vault` fixture pattern from `tests/server/test_scopes.py`, it is local to that file: `git init` in `tmp_path`, `mock.patch.object(<service>, "DEFAULT_ROOT", root)`, lint and autodeploy mocked); the real vault is never written. Send `{"Origin": "http://127.0.0.1:8765"}` on mutations and cover the 4xx shape.
8. **Regenerate the client.** `pixi run api-schema` rewrites `web/src/api/schema.d.ts`; commit it with the change. `pixi run api-schema-check` fails when it is stale (run it before `ship pr`).
9. **Verify.** `pixi run test` (or `pytest tests/server/test_<resource>.py` while iterating), `pixi run lint`, `pixi run api-schema-check`.
10. **Ship.** `ship commit`, `ship pr`, give the link; merge only when the user says merge.

## Subprocess note

A nested `claude -p` (or any child that may read stdin) must be started with `stdin=subprocess.DEVNULL`, or it waits forever.

## Output

New or changed files under `src/kb_distillery/{server,services}/`, `tests/`, and `web/src/api/schema.d.ts`. No vault content changes.

## Quality bar

- Router discovered without touching `app.py`; `/openapi.json` lists it
- `api-schema-check` and `pixi run test` pass
- No filesystem path literal outside `kb_distillery.config.paths`; no `sys.path.insert`
- Router has no business logic; service has no FastAPI import

## Next step

If the frontend should consume the new endpoint, hand off to `app-ui`.
