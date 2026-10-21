---
name: kb-history
description: >-
  Show the knowledge version, recent steps (kb-x.y.z) and infra PRs (#N), open sessions and pending
  commits. Use for kb history, what changed, kb status, current version, audit, debug a note's history.
  Do NOT use to change anything (read-only).
---

# kb-history

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `kb history`, `what changed`, `kb status`, `which version are we on`, `when did <slug> change`

## Do NOT

- Run git write commands — this skill is read-only
- Guess versions — read them from `ops log` / `ops status`

## CLI

```bash
pixi run ops -- status
pixi run ops -- log -n 30
pixi run ops -- log --kb
pixi run ops -- log --infra
pixi run ops -- snapshots
pixi run ops -- next-version
```

Plain git is fine for detail: `git log --first-parent --oneline`, `git show <sha>`, `git log -- wiki/<slug>.md`.
The dashboard Lifecycle tab (`pixi run dashboard` → `/lifecycle`) shows the same data.

Uncommitted knowledge from before the lifecycle (or a failed op) can be committed in labelled groups:
`pixi run ops -- record catalog lior-wolf "Lior Wolf profile and 4 papers" wiki/lior-wolf.md …` — only on the user's request.

## Agent steps

1. `pixi run ops -- status` for version, sessions, hooks and pending labels.
2. `pixi run ops -- log` (or `--kb` / `--infra`) for the steps; cite versions and shas.
3. For one note: `git log --first-parent --format='%h %s' -- wiki/<slug>.md`.

## Output

None — read-only report.

## Next step

`kb-undo` or `kb-snapshot` restore if the user wants to go back.
