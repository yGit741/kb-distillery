---
name: app-ui
description: >-
  Rules for building screens in the React app under frontend/ (tokens, components, one palette,
  data-model vocabulary, porting checklist). Use for port a screen, add a screen, frontend,
  app shell, shadcn component, data palette. Do NOT use for the legacy backend/src/kb/dashboard pages or wiki edits.
---

# app-ui

**LLM tier:** none · **Budget:** 0 tokens

Conventions for `frontend/` (Vite + React 19 + TypeScript strict + Tailwind v4 + shadcn/ui + TanStack Router/Query + zustand + vitest). Tooling: ships through an `infra/<feature>` PR (`infra-pr`).

## Triggers

- `port the <screen>`, `add a screen`, `frontend`, `app shell`, `app-ui`

## Do NOT

- Edit `wiki/`, `raw/`, `think/`, or the legacy pages in `backend/src/kb/dashboard/` (a port deletes its legacy page in the same PR, nothing else)
- Hard-code a colour, a second theme toggle, a second nav, or a second Markdown renderer

## CLI

```bash
pixi run web-install
pixi run web-dev
pixi run web-check
pixi run web-build
pixi run lint-skills
```

## Tokens

- `frontend/src/index.css` holds the shadcn CSS variables converted from `backend/src/kb/dashboard/static/shell.css` (light in `:root`, dark in `.dark`). ONE accent (`--primary`, blue). Chrome status colours are `--ok --warn --bad` only.
- Use Tailwind token classes (`bg-card`, `text-muted-foreground`, `border`, `text-primary`). Never a hex value in a component.
- Data colours (type, layer, depth, status, area, raw pile) come from `src/theme/palette.ts` and nowhere else.
- Theme: `src/theme/theme.ts` (zustand, saved in `localStorage` inside try/catch, `prefers-color-scheme` default). The toggle lives in AppShell only.
- Layout: 16px side gutters (`px-4`), no horizontal page scroll at phone width. Wide tables go in an `overflow-x-auto` wrapper.

## Components

- Prefer a shadcn-style primitive in `src/components/ui/`; add new ones there, hand-written in the same style.
- Screens live in `src/features/<screen>/index.tsx` and are discovered by convention in `src/routes/registry.ts` (that list drives nav, palette and router; metadata in `routes/defs.ts`). A screen reads data through `useDataSource()` + TanStack Query, never `fetch` and never globals.
- Every screen handles loading (skeleton), error (message + retry) and empty states.
- Cross-screen client state (selection, drafts) goes in zustand; server state in Query; URL-worthy state in router search params.

## Data-model vocabulary

The frontend speaks the shipped model (schema 1.0, `meta/schema.py` `LAYER_OF`; `src/api/model.ts` mirrors it): every page has a `layer` (`source`, `collection`, `concept`) and a `type` inside it.

- source: paper, part, lecture, article, video, conversation, ai-chat, blog-post. Sources alone carry `depth`: `listed`, `easy`, `full`, `deep`.
- collection: book, notebook, course, series, plus aux `scope`.
- concept: idea, topic, question, person, plus aux `distilled-think`.

The backend emits these names directly, so there is no translation layer and no `kind`: palette keys, props, stores, filters, labels and test names use `layer`, `type` and `depth` as the API returns them. Retired words (hub, MOC, reading unit, theme or bare concept as a type, `catalog` as a depth, `digestion-status`) must not appear.

## De-duplication rules

1. One control per action, one place per setting. A PR lists the controls it removed or merged.
2. One nav, one theme toggle, one ⌘K palette (all in AppShell). Screens add palette commands by extending the palette, not by opening their own.
3. One `<Markdown>` renderer (Markdown + KaTeX + `[[slug]]` links) in `src/components/`; chat and pages must not each carry a copy.
4. One data palette; no per-screen colour maps.
5. No re-parenting or clicking hidden legacy buttons: a ported screen has one toolbar.

## Porting checklist

The app is served under `/app` (vite `base`, router `basepath`; `python -m kb.api` and `pixi run web-dev` both work). The groundwork is shared, so a screen port adds **only files inside its own folder** and never edits a shared file.

1. Read the legacy page, its `*_data.py` and its `/api/*` response. Types come from the generated `src/api/schema.d.ts` (`pixi run api-schema`; short names in `src/api/types.ts`). Never hand-write a response shape.
2. Data: call `useApiQuery(key, (ds) => ds.<method>())` (or `useDataSource()` + `useQuery`). `DataSource` already has one method per endpoint group (pages, search, path, graph, corpus, raw, scopes, pipeline, chat incl. `chatStream`, ops, health). A missing endpoint is a backend PR first, then one line each in `datasource.ts`, `http.ts`, `embedded.ts`.
3. Screen: replace `src/features/<id>/index.tsx` (`id` = chat, pages, graph, scopes, pipeline, ...). Default export = the screen component; add `export const ported = true;`. The registry picks the folder up by convention (`import.meta.glob`), so nav, palette and router need no edit. Put the screen's other files next to `index.tsx`.
4. URL state: the typed search params for the id are in `src/routes/search.ts` (`SearchById`); read them with `useSearch({ strict: false }) as SearchById["<id>"]`. If you need another param, add it there in the same PR; nothing else shared changes.
5. Cross-screen state (selected slugs, open scope draft) is `useKb()` from `src/lib/store.ts`; do not add a second store for it.
6. Reuse the shared pieces: `<Markdown>` (`src/components/Markdown.tsx`, GFM + KaTeX + `[[slug]]` links to `/pages/<slug>`, `resolveSlug` prop), `Loading` / `Empty` / `ErrorState` / `ErrorBoundary` (`src/components/states.tsx`), `src/theme/palette.ts`, tokens. List the duplicates you removed.
7. Tests next to the screen: render with `mockDataSource({...})` from `src/test/datasource.ts` (loading, error, empty, data) plus unit tests for pure logic.
8. `pixi run web-check`, commit `frontend/dist`, then check `/app/<path>` in a browser (hard reload, light and dark, 390px without horizontal scroll, no console errors) against `python -m kb.api --port <spare>`.
9. Delete the legacy page and its static files in the same PR.

## Output

Changes under `frontend/` (including the committed `frontend/dist`); no vault changes.
