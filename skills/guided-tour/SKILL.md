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

1. The tool is shared and ships in every build (app and share snapshots): engine `frontend/src/features/tour/engine.ts`,
   registry `frontend/src/features/tour/tours.ts` (installed once in `main.tsx`). Never fork it.
2. In the feature that owns the screen, add `<feature>/tours.ts` calling `registerTour("<name>", steps)` with
   `{ target, title, body, place?, pad?, before? }`, and import it from that feature's screen
   (example: `frontend/src/features/graph/tours.ts`).
   - Target real elements by `aria-label` (toolbar buttons, `section[aria-label="<panel>"]`), not classes.
   - `before` opens what the step needs (`clickUnlessOpen(button, section)`); targets are awaited up to 2 s.
   - One idea per step, 4–8 steps, body ≤ 2 sentences.
3. Open `?tour=<name>` (or `kbTour.start("<name>")` in the console) and screenshot a few steps as proof.
4. Ship through `infra-pr`.

## Output

A named tour in the app; nothing in the vault changes.
