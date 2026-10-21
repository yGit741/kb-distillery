---
name: infra-pr
description: >-
  Ship tooling (dashboard, explorer, ingest CLI, skills, schema) through an infra/<feature> branch and a
  GitHub PR merged with a real merge commit "(#N)". Use for ship, open PR, merge PR, infra change, schema
  change, release tooling. Do NOT use for knowledge edits (they commit on main via ops) and only when the user asks.
---

# infra-pr

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `ship`, `open a PR`, `merge the PR`, `ship the dashboard change`, `schema change`
- Only on the user's request — never ship on your own initiative

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

1. Work in a worktree: `pixi run ship -- start <feature> --worktree` (or, inside a session worktree, `ship -- start <feature>` renames its branch to `infra/<feature>`).
2. Commit with `ship -- commit "type(component): imperative summary"` — types by what changed: `schema` (note rules) › `feat` (new capability) › `fix` (wrong behaviour) › `chore` (no behaviour change: config, docs, tests, refactors); scope is a component (`vault raw books think ingest lint guard dashboard skills distill query export scrap git obsidian claude gemini`). Gates: unit tests, lint-skills, lint. Untracked raw PDFs are linked from the primary checkout automatically.
3. `ship -- pr` pushes and opens the PR (idempotent). Pass `--title` when the branch has several commits.
4. When the user approves: `ship -- merge` → merges main into the branch if needed, re-runs gates, merges as `<title> (#N)`, deletes the remote branch, fast-forwards the primary checkout.
5. **Schema PR:** bump `SCHEMA_VERSION` in `meta/schema.py`, add `meta/migrations/NNNN_<name>.py` (`PRODUCES`, idempotent `apply(root)`), run `pixi run ops -- migrate` on the branch, commit as `schema(<scope>): …`. `ship -- merge` snapshots the current version and sets `KB-Version: x.(y+1).0` on the merge.

## Output

A merge commit on main `type(scope): summary (#N)`; tooling is unversioned, schema/paradigm merges bump the knowledge version.

## Next step

`pixi run launch` to reload the dashboard; `kb-history` to see the merge.
