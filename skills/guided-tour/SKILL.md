---
name: guided-tour
description: >-
  Add a first-run style guided tour to the real app (screen dimmed, one element spotlit, explainer card beside
  it, fixed Back / Next / Skip dock). Use for guided tour, walkthrough, onboarding tour, tour of a screen or
  panel. Do NOT use to redesign or implement the screen itself (app-ui) or for wiki edits.
---

# guided-tour

**LLM tier:** light · **Budget:** ~2–4k tokens

## Triggers

- `guided tour`, `walkthrough`, `onboarding tour`, `tour of the <screen>`

## Do NOT

- Change the UI the tour explains — tours only point at what exists
- Write in `raw/`, `think/` or `wiki/`

## CLI

```bash
pixi run app    # then open http://127.0.0.1:8765/graph?tour=experiments
```

## Agent steps

1. Engine: `frontend/src/features/tour/engine.ts` (`startTour(steps)`); never fork it.
2. Add the tour to `TOURS` in `frontend/src/features/tour/tours.ts`: `{ target, title, body, place?, pad?, before? }`.
   - Target real elements by `aria-label` (toolbar buttons, `section[aria-label="<panel>"]`), not classes.
   - `before` opens what the step needs (e.g. `openPanel("Experiments")`); targets are awaited up to 2 s.
   - One idea per step, 4–8 steps, body ≤ 2 sentences.
3. Open `?tour=<name>` (or `kbTour.start("<name>")` in the console) and screenshot a few steps as proof.
4. Ship through `infra-pr`.

## Output

A named tour in the app; nothing in the vault changes.
