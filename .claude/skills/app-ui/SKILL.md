---
name: app-ui
description: >-
  Rules for building screens in the React app under frontend/ (tokens, components, one palette,
  data-model vocabulary, porting checklist). Use for port a screen, add a screen, frontend,
  app shell, shadcn component, data palette. Do NOT use for the legacy meta/dashboard pages or wiki edits.
---

# app-ui

**LLM tier:** none · **Budget:** 0 tokens

Conventions for `frontend/` (Vite + React 19 + TypeScript strict + Tailwind v4 + shadcn/ui + TanStack Router/Query + zustand + vitest). Tooling: ships through an `infra/<feature>` PR (`infra-pr`).

## Triggers

- `port the <screen>`, `add a screen`, `frontend`, `app shell`, `app-ui`

## Do NOT

- Edit `wiki/`, `raw/`, `think/`, or the legacy pages in `meta/dashboard/` (a port deletes its legacy page in the same PR, nothing else)
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

- `frontend/src/index.css` holds the shadcn CSS variables converted from `meta/dashboard/static/shell.css` (light in `:root`, dark in `.dark`). ONE accent (`--primary`, blue). Chrome status colours are `--ok --warn --bad` only.
- Use Tailwind token classes (`bg-card`, `text-muted-foreground`, `border`, `text-primary`). Never a hex value in a component.
- Data colours (type, kind, depth, status, area, raw pile) come from `src/theme/palette.ts` and nowhere else.
- Theme: `src/theme/theme.ts` (zustand, saved in `localStorage` inside try/catch, `prefers-color-scheme` default). The toggle lives in AppShell only.
- Layout: 16px side gutters (`px-4`), no horizontal page scroll at phone width. Wide tables go in an `overflow-x-auto` wrapper.

## Components

- Prefer a shadcn-style primitive in `src/components/ui/`; add new ones there, hand-written in the same style.
- Screens live in `src/features/<screen>/` and are registered in `src/routes/registry.ts` (that list drives nav, palette and router). A screen reads data through `useDataSource()` + TanStack Query, never `fetch` and never globals.
- Every screen handles loading (skeleton), error (message + retry) and empty states.
- Cross-screen client state (selection, drafts) goes in zustand; server state in Query; URL-worthy state in router search params.

## Data-model vocabulary

New code speaks only the data model: page `type` (`source`, `collection`, `concept`), `kind` (`paper article blog-post video lecture conversation ai-chat part`; `book notebook course series`; `idea topic question person`) and source `depth` (`catalog easy full deep`). Palette keys, props, stores, filters, labels and test names use only these words. Retired words (hub, MOC, theme as a type, container, reading unit, digestion-status as a field) must not appear.

The only place old names may appear is `src/api/legacyModel.ts` (marked DELETE after data-model stage 7). The http DataSource passes backend data through it at the boundary.

## De-duplication rules

1. One control per action, one place per setting. A PR lists the controls it removed or merged.
2. One nav, one theme toggle, one ⌘K palette (all in AppShell). Screens add palette commands by extending the palette, not by opening their own.
3. One `<Markdown>` renderer (Markdown + KaTeX + `[[slug]]` links) in `src/components/`; chat and pages must not each carry a copy.
4. One data palette; no per-screen colour maps.
5. No re-parenting or clicking hidden legacy buttons: a ported screen has one toolbar.

## Porting checklist

1. Read the legacy page, its `*_data.py` and its `/api/*` response; write the response types by hand in `src/api/types.ts` (generated once the OpenAPI schema lands).
2. Add the method to the `DataSource` interface, `http.ts`, and the `embedded.ts` stub. Translate old names in `legacyModel.ts` only.
3. Build the screen in `src/features/<screen>/`; flip `ported: true` in the registry.
4. Use the palette, tokens, and shared components; list removed duplicates.
5. Tests: render test with a mocked DataSource (loading, error, empty, data) plus unit tests for pure logic.
6. `pixi run web-check`, commit `frontend/dist`, then check light and dark and a 375px viewport.
7. Delete the legacy page and its static files in the same PR.

## Output

Changes under `frontend/` (including the committed `frontend/dist`); no vault changes.
