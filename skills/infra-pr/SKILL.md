---
name: infra-pr
description: >-
  Fix, change or add tooling (dashboard, explorer, graph, ingest CLI, skills, lint, schema) via an
  infra/<feature> branch and a GitHub PR merged as "(#N)". Use for fix the …, change the …, add a feature,
  bug in the dashboard or pipeline, ship, open PR, merge PR, schema change. Do NOT use for knowledge
  edits in wiki/ (use wiki-edit). Merges its own PRs unless held (schema/paradigm or the user asked to review).
---

# infra-pr

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `ship`, `open a PR`, `merge the PR`, `ship the dashboard change`, `schema change`
- Any user request to fix/change/add tooling ("fix the legend", "the graph should …") — start the flow and return the PR link
- Never on your own initiative; once asked, carry it through to the merge — multi-PR asks merge each PR and continue
- Hold (`ship pr --hold`) when the user said "don't merge", "let me review" or similar; schema/paradigm PRs are held automatically

## Do NOT

- Commit tooling on main, squash or rebase a PR — `ship` refuses; merges are always merge commits
- Mix knowledge edits into a feature PR — only `schema`/`paradigm` PRs carry migrated notes
- Run `git commit` / `git push` / `gh pr` directly — blocked; `pixi run ship` is the path

## CLI

```bash
pixi run ship -- start graph-legend --worktree
pixi run ship -- commit "feat(dashboard): graph legend redesign"
pixi run ship -- pr --title "feat(dashboard): graph legend redesign"
pixi run ship -- pr --hold                      # the user wants to review it
pixi run ship -- merge
pixi run ship -- approve 12                     # USER ONLY (blocked for agents); or the owner's GitHub Approve review
pixi run ship -- status
pixi run ship -- claims                         # every lane's claimed / touched paths
pixi run ship -- events 12                      # kb-event lines on PR 12 (claimed, queued, checks, merged)
pixi run ship -- round open "Phase 2" --features a,b   # multi-PR effort: issue #R with a checklist
pixi run ship -- start a --worktree --round 40    # link the branch; pr/merge mirror events + tick on #40
pixi run ship -- round status 40                # checklist + latest event per feature (one line each)
pixi run ops -- migrate --check
```

## Agent steps

1. Work in a worktree: `pixi run ship -- start <feature> --worktree --paths <dir>,<dir>` (`--paths` claims the dirs you will touch and prints an OVERLAP warning when another open PR or worktree touches them — tell the user, never stop on it; `ship -- claims` lists all lanes) (or, inside a session worktree, `ship -- start <feature>` renames its `worktree-*` branch to `infra/<feature>` — do this **before the first edit**; a session must never end on a `worktree-*` branch: finish with `ship -- pr` or `ship -- prune --drop <branch>`).
2. Commit with `ship -- commit "type(component): imperative summary"` — types by what changed: `schema` (note rules) › `feat` (new capability) › `fix` (wrong behaviour) › `chore` (no behaviour change: config, docs, tests, refactors); scope is a component (`vault raw books think ingest lint guard dashboard skills distill query export scrap git obsidian claude gemini`). Gates: unit tests, lint-skills, lint. Untracked raw PDFs are linked from the primary checkout automatically.
3. **Review first:** spawn the read-only `reviewer` subagent (`.claude/agents/reviewer.md`) on the branch and fix its blocking findings. Then `ship -- pr`, which also runs the scripted check gate (no LLM) for the lanes the branch touched vs origin/main: `frontend/` → `web-check`, `backend/src/kb/api/` or `frontend/src/api` → `api-schema-check`, `backend/src/kb/dashboard/` → `test-e2e` (skipped with a note when node/playwright is missing). It refuses on failure and prints the output tail; `--skip-checks "<reason>"` bypasses it and the reason lands in the PR body. `ship -- merge` runs the same gate.
   `ship -- pr` pushes and opens the PR (idempotent). Pass `--title` when the branch has several commits — its type must be the highest of them (paradigm › schema › feat › fix › chore) and the whole `<title> (#N)` must fit 100 chars; `ship` refuses otherwise. Add `--hold` when the user wants to review it; schema/paradigm PRs get the `hold` label automatically.
4. **Not held → merge it yourself:** `ship -- merge` → merges main into the branch if needed, re-runs gates, merges as `<title> (#N)`, deletes the remote branch, fast-forwards the primary checkout, then removes the worktree and local branch (continue in the primary checkout — its path is printed). Report the merged PR as `#N title`. **Held →** stop; `ship merge` refuses until the user approves: a GitHub **Approve** review by the owner on the current head sha (phone app works; then `ship -- merge` lifts the hold and merges; new commits → "re-approve") or `! pixi run ship -- approve N` (agents are blocked from `approve`, `gh pr review` and editing labels). `ship -- status` shows each held PR as `approved ✓ (sha ok)` / `approved on old sha` / `awaiting review`. Until then **end every reply** with `Awaiting your merge: #N <title> <url> — approve the review on GitHub, or run \`! pixi run ship -- approve N\` to merge it, or say "drop".` (the `Stop` hook `backend/src/kb/git/merge_nudge.py` enforces it once per reply). `pixi run lanes` shows anything left behind; `ship -- prune --apply` clears merged clean worktrees.
5. **Feature flag:** a feature that can't land in one PR ships dark behind a new `[[flag]]` in `meta/flags.toml` (needs `owner`, `expires` ≤ 90 days after `created`) and merges in small PRs; add tests for **both** states (`@pytest.mark.flag(name, True|False)` / `withFlag(name, true|false, …)` — `flags-check` fails otherwise); release = flipping the flag, not deploying. Expired flags are a lint error — remove them with `meta/templates/flag-cleanup-pr.md`.
6. **Schema PR:** bump `SCHEMA_VERSION` in `backend/src/kb/core/schema.py`, add `backend/src/kb/migrations/NNNN_<name>.py` (`PRODUCES`, idempotent `apply(root)`), run `pixi run ops -- migrate` on the branch, commit as `schema(<scope>): …`. `ship -- merge` snapshots the current version (`pre-<feature>`), sets `KB-Version: x.(y+1).0` on the merge and tags it as the new baseline (`post-<feature>`). A **paradigm** PR (`paradigm(<scope>): …`, e.g. schema 1.0, the source model) works the same way but bumps x: `(x+1).0.0`.

## Output

A merge commit on main `type(scope): summary (#N)`; tooling is unversioned, schema/paradigm merges bump the knowledge version.

## Next step

`pixi run launch` to reload the dashboard; `kb-history` to see the merge.
