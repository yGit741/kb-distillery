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

The frontend speaks the shipped model (schema 1.0, `backend/src/kb/core/schema.py` `LAYER_OF`; `src/api/model.ts` mirrors it): every page has a `layer` (`source`, `collection`, `concept`) and a `type` inside it.

- source: paper, part, lecture, article, video, mail, ai-chat, blog-post. Sources alone carry `depth`: `listed`, `easy`, `full`, `deep`.
- collection: book, notebook, course, series, plus aux `scope`.
- concept: idea, topic, question, person, plus aux `distilled-think`.

The backend emits these names directly, so there is no translation layer and no `kind`: palette keys, props, stores, filters, labels and test names use `layer`, `type` and `depth` as the API returns them. Retired words (hub, MOC, reading unit, theme or bare concept as a type, `catalog` as a depth, `digestion-status`) must not appear.

## Rendering rules

1. Loading, empty and error states render inside the same container as the content, so the layout does not jump.
2. A colour tint appears only when a value signals a problem; healthy values stay neutral.
3. Add no controls the spec did not ask for.
4. No Markdown syntax (`**`, backticks, `#`) inside JSX text; use elements, or `<Markdown>` for real Markdown.

## De-duplication rules

1. One control per action, one place per setting. A PR lists the controls it removed or merged.
2. One nav, one theme toggle, one ⌘K palette (all in AppShell). Screens add palette commands by extending the palette, not by opening their own.
3. One `<Markdown>` renderer (Markdown + KaTeX + `[[slug]]` links) in `src/components/`; chat and pages must not each carry a copy.
4. One data palette; no per-screen colour maps.
5. No re-parenting or clicking hidden legacy buttons: a ported screen has one toolbar.

## Design layers

This skill is the **project** layer. Two global skills sit above it and win on conflict:

1. `ui-principles` — rules that are always right (stability, no overlap, contrast, colour meaning and Stroop,
   one central status/ramp scheme, cognitive load, icon consistency, motion, legends vs data).
2. `ui-taste` — the owner's preferences (calm and soft, minimal chrome, icons chosen from several options,
   modest copy, desktop first).

Precedence: principles > taste > this file > convenience. Before merging a UI PR, run `ui-review` on the changed
screens. Code that still breaks a rule is a backlog item for its own PR, not an exception in this file.

## Graph feature design

The graph (`src/features/graph`) is the app's core view. These rules apply to every view of it and to every
mini-graph embedded elsewhere (Home cards). **A view (story) only chooses what counts as important; it never breaks
a rule below.**

### Consistency across screens
1. **The same view everywhere.** A mini-graph and the full graph use the same marks, legend and colouring; moving
   between screens never changes what a colour or shape means. "Open in Full Graph" shows exactly the pages the
   card drew, in the same colouring.
2. **One central colour scheme**: status (ok / warn / fail) and every ordered ramp come from `src/theme/palette.ts`;
   no view defines its own.

### Labels
3. **Budget**: about 12% of the canvas, roughly 20–40 labels at fit (Bobák 2024).
4. **Chosen over the whole graph, not what is on screen**, so panning never changes the set (pan churn fell from
   71–174 to 5–18 label changes/s in the Label Lab; Been 2006).
5. **Ranked by degree of interest normalised per type, never raw degree** (imports skew degree: the Kalai blog
   series has 1,401 links; Furnas; van Ham & Perer).
6. **Size follows importance rank** (top 5% / next 20% / rest), so being shown and being big mean the same thing;
   label size grows with √zoom and never drops below 11 px (Töpfer).
7. **Display names, not slugs**; drop what the mark already says (no leading "?" on a question).
8. **Never cut a word; no "…" when there is room.** Long-titled types (questions) show their glyph at rest and the
   full title on hover or click. A label that can't sit beside its node moves out with a leader line in the node's
   own colour.
9. **Hover**: a soft glow in the page's own colour and its full title, no solid pills. A click labels at most ~6
   strongest neighbours, chosen by stable edge weight.

### Colour meaning (no Stroop conflicts)
10. **Shape is the type, colour is the view.** Type is carried by the mark in a sticky key; colour answers the
    current view's question in its own key. Colouring by type in a view that already shows type by shape is a
    conflict, so that view colours by area instead (`effectiveColorBy`).
11. **A colour never contradicts its learned meaning**: red/amber only for problems; people, "No area" and edges
    each get a colour no other meaning uses (people a deep ink, "No area" a ring, edges a light grey).
12. **Categories**: ≤ 12 area hues assigned by size, the rest "Other areas" in grey; "Other" and "No area" always
    sort last. **Ordered measures**: one lightness ramp with a stepped bar legend, never unordered hues.
13. **Colour-by offers only colourings that answer a real question**; remove ones that change nothing.

### Marks
14. **One mark per type, the same at every zoom**: source = dot (glyph from ~7 px radius or on hover: page = paper,
    sparkle = AI chat, envelope = mail, play = lecture, book = part), question = ring with "?", idea = ring with dot,
    topic = ring with lines, collection = double ring, person = initials. Hollow marks drawn ~15% larger.
15. **Size means importance per layer**: an idea is never smaller than a median paper, a person never smaller than
    a median idea; node screen size grows with √zoom (semantic zoom).

### Legend and filters
16. **The legend lists every encoding on screen**: "Concepts: … | Sources: …" (collections folded into sources),
    wrapping rather than cutting, with counts that say what they count.
17. **The legend is a filter**: a group toggles its layer, a chip its type, hover spotlights with the same
    hysteresis as node hover; hidden rows stay listed.
18. **Quick filters are filters, not insights** (Recent, Connected); every active filter shows a × and a "Clear"
    appears while any is on.

### Layout and interaction
19. **Fit after the layout settles**, and stop refitting once the user pans or zooms.
20. **Topics anchored on a ring**; hulls truly round (Minkowski sum) and shown only when colour doesn't already
    say the same thing.
21. **Hover dims lightly or not at all; only a selection dims the rest.** Hover commits on intent (dwell ~150 ms,
    fade 180 ms in / 100 ms out) with hysteresis against flicker.
22. **Mouse**: left-drag pans, wheel zooms at the cursor, right-click opens the node menu, right-click on empty
    space clears the selection, double-click opens the side reader.
23. **Default views are sparse**: concepts first, sources on demand.
24. **Embedded mini-graphs never capture page scroll** and a tiny sample never blows up to fill its card.
25. **Engine facts**: force-graph radius = √nodeVal; size the canvas after layout; fit to the dense core; never
    `setPointerCapture` or put pointer-taking overlays over the canvas; cursors as blob URLs.

## Porting checklist

The app is served under `/app` (vite `base`, router `basepath`; `python -m kb.api` and `pixi run web-dev` both work). The groundwork is shared, so a screen port adds **only files inside its own folder** and never edits a shared file.

1. Read the legacy page, its `*_data.py` and its `/api/*` response. Types come from the generated `src/api/schema.d.ts` (`pixi run api-schema`; short names in `src/api/types.ts`). Never hand-write a response shape.
2. Data: call `useApiQuery(key, (ds) => ds.<method>())` (or `useDataSource()` + `useQuery`). `DataSource` already has one method per endpoint group (pages, search, path, graph, corpus, raw, scopes, pipeline, chat incl. `chatStream`, ops, health). A missing endpoint is a backend PR first, then one line each in `datasource.ts`, `http.ts`, `embedded.ts`.
3. Screen: replace `src/features/<id>/index.tsx` (`id` = chat, pages, graph, scopes, pipeline, ...). Default export = the screen component; add `export const ported = true;`. The registry picks the folder up by convention (`import.meta.glob`), so nav, palette and router need no edit. Put the screen's other files next to `index.tsx`.
4. URL state: the typed search params for the id are in `src/routes/search.ts` (`SearchById`); read them with `useSearch({ strict: false }) as SearchById["<id>"]`. If you need another param, add it there in the same PR; nothing else shared changes.
5. Cross-screen state (selected slugs, open scope draft) is `useKb()` from `src/lib/store.ts`; do not add a second store for it.
6. Reuse the shared pieces: `<Markdown>` (`src/components/Markdown.tsx`, GFM + KaTeX + `[[slug]]` links to `/pages/<slug>`, `resolveSlug` prop), `Loading` / `Empty` / `ErrorState` / `ErrorBoundary` (`src/components/states.tsx`), `src/theme/palette.ts`, tokens. List the duplicates you removed.
7. Tests next to the screen: render with `mockDataSource({...})` from `src/test/datasource.ts` (loading, error, empty, data) plus unit tests for pure logic.
8. `pixi run web-check` (never commit `frontend/dist` — it is gitignored build output; restarting `kb.api` rebuilds it), then check `/app/<path>` in a browser (hard reload, light and dark, 390px without horizontal scroll, no console errors) against `python -m kb.api --port <spare>`.
9. Delete the legacy page and its static files in the same PR.

## Output

Changes under `frontend/` (sources only — `frontend/dist` is build output and never committed); no vault changes.
