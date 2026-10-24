---
name: guided-tour
description: >-
  Build a first-run style guided tour (page dimmed, one element spotlit, Next / Back / Skip) over an HTML
  mockup, to pitch or explain a UI before implementing it. Use for guided tour, walkthrough, onboarding tour,
  tour of a design. Do NOT use to implement the UI in frontend/ (app-ui) or for wiki edits.
---

# guided-tour

**LLM tier:** light · **Budget:** ~2–4k tokens

## Triggers

- `guided tour`, `walkthrough`, `onboarding tour`, `tour of this design`

## Do NOT

- Change `frontend/` — a tour is a pitch artifact; implementation goes through `app-ui` + `infra-pr`
- Write in `raw/`, `think/` or `wiki/`

## CLI

```bash
python3 skills/guided-tour/build.py skills/guided-tour/examples/noise-stability.html -o .cache/tour.html
```

## Agent steps

1. Write the mockup HTML: static markup with stable `id`s on everything a step points at, and the marker
   `<!-- tour.js -->` before the script that calls the engine.
2. Describe the steps in that script: `Tour.start([{ target, title, body, place, before }])`.
   One idea per step, 4–8 steps, body ≤ 2 sentences. `before` can switch the mockup's state (open a panel).
3. Add a "Start tour" button and start the tour on load.
4. Build with `build.py` (inlines `assets/tour.js`), then publish the output with the Artifact tool.
5. Theme with `--gt-bg`, `--gt-fg`, `--gt-muted`, `--gt-accent` on `:root`.

## Output

One self-contained HTML file (an artifact); nothing in the vault changes.
