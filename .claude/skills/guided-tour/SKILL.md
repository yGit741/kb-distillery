---
name: guided-tour
description: >-
  Add a first-run style guided tour to the real app (screen dimmed, one element spotlit, explainer card beside
  it, fixed Back / Next / Skip dock), or send a one-off show-me link that explains something on screen instead
  of in chat. Use for guided tour, walkthrough, onboarding tour, tour of a screen or panel, show me, show-me,
  explain this on the UI, any reply about something visible in the app. Do NOT use to redesign or implement
  the screen itself (app-ui) or for wiki edits.
audience: dev
mode: write
---

# guided-tour

**LLM tier:** light · **Budget:** ~2–4k tokens

## Triggers

- `guided tour`, `walkthrough`, `onboarding tour`, `tour of the <screen>`
- **Show-me:** whenever a reply is about something on screen (a change you made, a bug you found, where a
  control lives, a question about a layout) — show it instead of describing it

## Do NOT

- Change the UI the tour explains — tours only point at what exists
- Write in `raw/`, `think/` or `wiki/`

## CLI

```bash
pixi run app    # then open http://127.0.0.1:8765/graph?tour=experiments
```

## Agent steps

1. The tool is shared and ships in every build (app and share snapshots): engine `web/src/features/tour/engine.ts`,
   registry `web/src/features/tour/tours.ts` (installed once in `main.tsx`). Never fork it.
2. In the feature that owns the screen, add `<feature>/tours.ts` calling `registerTour("<name>", steps)` with
   `{ target, title, body, place?, pad?, before? }`, and import it from that feature's screen
   (example: `web/src/features/graph/tours.ts`).
   - Target real elements by `aria-label` (toolbar buttons, `section[aria-label="<panel>"]`), not classes.
   - `before` opens what the step needs (`clickUnlessOpen(button, section)`); targets are awaited up to 2 s.
   - One idea per step, 4–8 steps, body ≤ 2 sentences.
3. Open `?tour=<name>` (or `kbTour.start("<name>")` in the console) and screenshot a few steps as proof.
4. Ship through `infra-pr`.

## Show-me — the agent's way to talk about the UI

A show-me is a throwaway tour in the link: write a JSON script, `pixi run show -- <file>` checks it and prints
a **local** and a **deployed** link (`?show=<base64url>`), put them in the reply. Nothing is registered,
committed or deployed; it plays on any build that has the engine. Keep the script in the scratchpad.

```json
{ "title": "Legend now says what the colours mean",
  "steps": [
    { "go": "/graph", "target": "section[aria-label=\"Legend\"]", "kind": "changed",
      "title": "The legend", "body": "Rows are now **one per layer**; [1] is the new count." ,
      "marks": [{ "target": "section[aria-label=\"Legend\"] .count", "kind": "new", "label": "count" }] },
    { "do": [{ "click": "nav[aria-label=\"Graph tools\"] button[aria-label=\"Search\"]" }, { "type": "input[type=search]", "text": "rank" }],
      "target": "[data-tour=\"graph-search\"]", "title": "Try it", "body": "Typing filters the legend too." } ] }
```

| Field | Meaning |
|---|---|
| `target` | the element in the spotlight (omit → card only) |
| `kind` / `marks[].kind` | colour = meaning, one each: `focus` look here (accent) · `new` added (green) · `changed` (amber) · `issue` problem (red) |
| `marks` | more elements lit at once, numbered ①②… with an optional `label`; refer to them as `[1]` in `body` |
| `do` | acts it out before the card shows: `{click}`, `{hover}`, `{type, text}`, `{press}`, `{wait}` (a dot glides to each element first) |
| `dim` | 0–0.85 how dark the rest gets (default 0.55; lower when the context matters) |
| `body` | ≤ 2 sentences; `**bold**` the one word that matters |
| `autoplay` | (top level) ms per step, for a hands-off demo or a recording |

UX rules it encodes (keep them): one idea per step (cognitive load); the spotlight and the dim do the pointing,
the text only says *why* (signalling); a mark always has a number and label, colour is never the only cue;
the same colour means the same thing in every show-me, and a `[n]` in the text wears its mark's colour; act it out rather than say "click X" (show, don't
tell); 3–6 steps. Target a real box (a panel, an `aside`, a button), not a `display: contents` wrapper whose
children are spread over the screen.

## Output

A named tour in the app; nothing in the vault changes.
