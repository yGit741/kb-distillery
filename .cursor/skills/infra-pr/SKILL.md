---
name: infra-pr
description: >-
  Fix, change or add tooling (dashboard, explorer, graph, ingest CLI, skills, lint, schema) via an
  infra/<feature> branch and a GitHub PR merged as "(#N)". Use for fix the …, change the …, add a feature,
  bug in the dashboard or pipeline, ship, open PR, merge PR, schema change. Do NOT use for knowledge
  edits in wiki/ (use wiki-edit) and do not merge until the user says merge.
---

# infra-pr

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `ship`, `open a PR`, `merge the PR`, `ship the dashboard change`, `schema change`
- Any user request to fix/change/add tooling ("fix the legend", "the graph should …") — start the flow and return the PR link
- Never on your own initiative; merge only when the user says merge (or "fix and merge")

## Do NOT

- Commit tooling on main, squash or rebase a PR — `ship` refuses; merges are always merge commits
- Mix knowledge edits into a feature PR — only `schema`/`paradigm` PRs carry migrated notes
- Run `git commit` / `git push` / `gh pr` directly — blocked; `pixi run ship` is the path

## CLI

```bash
pixi run ship -- start graph-legend --worktree
pixi run ship -- commit "feat(dashboard): graph legend redesign"
pixi run ship -- pr --title "feat(dashboard): graph legend redesign"
pixi run ship -- merge
pixi run ship -- status
pixi run ops -- migrate --check
```

## Agent steps

1. Work in a worktree: `pixi run ship -- start <feature> --worktree` (or, inside a session worktree, `ship -- start <feature>` renames its `worktree-*` branch to `infra/<feature>` — do this **before the first edit**; a session must never end on a `worktree-*` branch: finish with `ship -- pr` or `ship -- prune --drop <branch>`).
2. Commit with `ship -- commit "type(component): imperative summary"` — types by what changed: `schema` (note rules) › `feat` (new capability) › `fix` (wrong behaviour) › `chore` (no behaviour change: config, docs, tests, refactors); scope is a component (`vault raw books think ingest lint guard dashboard skills distill query export scrap git obsidian claude gemini`). Gates: unit tests, lint-skills, lint. Untracked raw PDFs are linked from the primary checkout automatically.
3. `ship -- pr` pushes and opens the PR (idempotent). Pass `--title` when the branch has several commits — its type must be the highest of them (paradigm › schema › feat › fix › chore) and the whole `<title> (#N)` must fit 100 chars; `ship` refuses otherwise. From now until it is merged or dropped, **end every reply** with `Awaiting your merge: #N <title> <url> — say "merge" to merge it, or "drop" to discard it.` (the `Stop` hook `meta/merge_nudge.py` enforces it once per reply).
4. When the user approves: `ship -- merge` → merges main into the branch if needed, re-runs gates, merges as `<title> (#N)`, deletes the remote branch, fast-forwards the primary checkout, then removes the worktree and local branch (continue in the primary checkout — its path is printed). `pixi run lanes` shows anything left behind (stale worktrees, open PRs, nightly sync); `ship -- prune --apply` clears merged clean worktrees.
5. **Schema PR:** bump `SCHEMA_VERSION` in `meta/schema.py`, add `meta/migrations/NNNN_<name>.py` (`PRODUCES`, idempotent `apply(root)`), run `pixi run ops -- migrate` on the branch, commit as `schema(<scope>): …`. `ship -- merge` snapshots the current version (`pre-<feature>`), sets `KB-Version: x.(y+1).0` on the merge and tags it as the new baseline (`post-<feature>`).

## Output

A merge commit on main `type(scope): summary (#N)`; tooling is unversioned, schema/paradigm merges bump the knowledge version.

## Next step

`pixi run launch` to reload the dashboard; `kb-history` to see the merge.
