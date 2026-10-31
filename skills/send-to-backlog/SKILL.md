---
name: send-to-backlog
description: >-
  Dump an idea, bug or an unstarted plan into the local backlog as one tidy card (title, why, kind, area, size).
  Use for send to backlog, add to backlog, backlog this, park this idea, save this plan for later, what is in the backlog.
  Do NOT use to ship work (infra-pr), to start a queued item overnight (work-all-night), or for wiki and think notes.
---

# send-to-backlog

**LLM tier:** none · **Budget:** 0 tokens

A queue for ideas that must not be lost and must not cost a PR. One markdown file per item in `.backlog/` (gitignored, in the primary checkout, shared by every worktree). You format the dump in-session; the CLI only stores it.

## Triggers

- `send to backlog`, `add to backlog`, `backlog this`, `park this`, `save this plan for later`, `what is in the backlog`

## Do NOT

- Commit anything: `.backlog/` is local state, never tracked
- Start the work the item describes (that is `infra-pr`); capturing is the whole job
- Write into `docs/ROADMAP.md` or `docs/plans/`: promoting an item there is a separate, explicit ask
- Make an LLM call from the CLI (there is none)

## CLI

```bash
pixi run backlog -- add --title "<short imperative>" --why "<one or two lines>" --kind idea --area dashboard --size m
pixi run backlog -- add --title "<plan title>" --plan <plan-file>
pixi run backlog -- list
pixi run backlog -- show <id>
pixi run backlog -- status <id> next
```

## Agent steps

1. **Format the dump.** `title`: short, imperative, no trailing period. `why`: what it buys, one or two lines in the user's words. `kind`: `idea`, `bug` or `plan`. `area`: the component (`dashboard`, `graph`, `ingest`, `skills`, `lint`, `api`, `app`, …) or empty. `size`: `s` an hour, `m` a PR, `l` several PRs.
2. **A plan not yet started** (a file under `~/.claude/plans/`, or the one just approved): pass `--plan <file>`. The text is copied (the source file is scratch) and the item records `base_sha`, the branch and the tracked repo paths the plan names, so its card can say whether it is still relevant. Its `plan_status` is `has-plan`; an idea without a file is `no-plan`. Only files the plan names count for drift (a plan that names just folders shows no drift), compared against `origin/main`.
3. **Run `add`**, then answer in one line: the id and the kind. Do not restate the card.
4. **Listing.** `list` prints one line per item grouped by status; the `drift` word at the end is the plan's relevance: `fresh` (nothing touched its paths since it was written), `drifted` (some commits did), `stale` (paths gone or 10+ commits: re-read before starting), `maybe-done` (a later commit subject matches the title: check before starting). The local app's Backlog screen shows the same cards.
5. **Status moves** (`inbox` → `next` → `doing` → `done` / `dropped`) only when the user says so.

## Output

One file `.backlog/<yyyymmdd>-<slug>.md`. No repository change.

## Next step

`pixi run app`, then open Backlog; or ask for a queue run with `work-all-night` using the `next` items.
