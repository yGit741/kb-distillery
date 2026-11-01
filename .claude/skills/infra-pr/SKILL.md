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
- Pipe `ship` through `| tail` hoping to catch a failure: every `commit`, `pr`, `merge` and `sync` ends with one `RESULT: ok|FAILED (...)` line, and a gate's full output is in `.cache/ship-gates/*.log` (a failing gate also prints its last 25 lines). Read a log or a big file with an offset and a limit, never whole: it stays in the conversation and is re-read on every later turn
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
2. Commit with `ship -- commit "type(component): imperative summary"` — types by what changed: `schema` (note rules) › `feat` (new capability) › `fix` (wrong behaviour) › `chore` (no behaviour change: config, docs, tests, refactors); scope is a component (`vault raw books think ingest lint guard dashboard skills distill query export scrap git obsidian claude gemini`). Refusals that need no gate (bad message, nothing to commit, unrelated files already staged) come first and cost nothing. Then the gates run on a **subset**: lint-skills, lint, and pytest on the test dirs mirroring the touched `src/kb_distillery/<pkg>`, the changed test files and always the top-level `tests/test_*.py` invariants; config (`pixi.toml`, `pyproject.toml`, `conftest.py`) or anything unmapped runs the full suite. Only the paths present before the gates are committed, minus generated files. Untracked raw PDFs are linked from the primary checkout automatically.
3. **Review first:** spawn the read-only `reviewer` subagent (`.claude/agents/reviewer.md`) on the branch and fix its blocking findings. Then `ship -- pr`, which also runs the scripted check gate (no LLM) for the lanes the branch touched vs origin/main: `web/` → `web-check`, `src/kb_distillery/api/` or `web/src/api` → `api-schema-check`, `src/kb_distillery/dashboard/` → `test-e2e` (skipped with a note when node/playwright is missing). It refuses on failure and prints the output tail; `--skip-checks "<reason>"` bypasses it and the reason lands in the PR body. `ship -- merge` runs the same gate.
   `ship -- pr` and `ship -- merge` run the **full** suite. A gate or check that already passed on exactly this content (a tree sha of the work tree, generated files and gitignored files left out, plus the KB; records in `.cache/ship-gates/reuse/`) prints `gate: <name> reused (<sha7>)` instead of running; a `commit` subset pass is never reused by `pr`/`merge`, and any edit, new file, KB change or merged-in main is a miss.
   **Only one gate run at a time on the machine:** the first real (not reused) gate or check of a `ship` run takes the shared `kb-gate.lock` in the git common dir and holds it for the whole sequence. If another lane is running its gates you see `gate slot: waiting for <branch> (pid …)`, then `gate slot: taken (waited Ns)`; just let it wait (gives up after `KB_GATE_WAIT`, default 45 min). A fully reused run never waits. Do not poll machine load or run gates by hand to dodge the queue; a dead holder frees the slot by itself.
   `ship -- pr` pushes and opens the PR (idempotent). Pass `--title` when the branch has several commits — its type must be the highest of them (paradigm › schema › feat › fix › chore) and the whole `<title> (#N)` must fit 100 chars; `ship` refuses otherwise. Add `--hold` when the user wants to review it; schema/paradigm PRs get the `hold` label automatically.
4. **Not held → merge it yourself:** `ship -- merge` → merges main into the branch if needed, re-runs gates, merges as `<title> (#N)`, deletes the remote branch, fast-forwards the primary checkout, then removes the worktree and local branch (continue in the primary checkout — its path is printed). Report the merged PR as `#N title`. **Held →** stop; `ship merge` refuses until the user approves: a GitHub **Approve** review by the owner on the current head sha (phone app works; then `ship -- merge` lifts the hold and merges; new commits → "re-approve") or `! pixi run ship -- approve N` (agents are blocked from `approve`, `gh pr review` and editing labels). `ship -- status` shows each held PR as `approved ✓ (sha ok)` / `approved on old sha` / `awaiting review`. Until then **end every reply** with `Awaiting your merge: #N <title> <url> — approve the review on GitHub, or run \`! pixi run ship -- approve N\` to merge it, or say "drop".` (the `Stop` hook `src/kb_distillery/git/merge_nudge.py` enforces it once per reply). `pixi run lanes` shows anything left behind; `ship -- prune --apply` clears merged clean worktrees.
5. **Feature flag:** a feature that can't land in one PR ships dark behind a new `[[flag]]` in `src/kb_distillery/kits/base/defaults/flags.toml` (needs `owner`, `expires` ≤ 90 days after `created`) and merges in small PRs; add tests for **both** states (`@pytest.mark.flag(name, True|False)` / `withFlag(name, true|false, …)` — `flags-check` fails otherwise); release = flipping the flag, not deploying. Expired flags are a lint error — remove them with `src/kb_distillery/kits/base/defaults/templates/flag-cleanup-pr.md`.
6. **Schema PR:** bump `SCHEMA_VERSION` in `src/kb_distillery/core/schema.py`, add `src/kb_distillery/migrations/NNNN_<name>.py` (`PRODUCES`, idempotent `apply(root)`), run `pixi run ops -- migrate` on the branch, commit as `schema(<scope>): …`. `ship -- merge` snapshots the current version (`pre-<feature>`), sets `KB-Version: x.(y+1).0` on the merge and tags it as the new baseline (`post-<feature>`). A **paradigm** PR (`paradigm(<scope>): …`, e.g. schema 1.0, the source model) works the same way but bumps x: `(x+1).0.0`.

## Output

A merge commit on main `type(scope): summary (#N)`; tooling is unversioned, schema/paradigm merges bump the knowledge version.

## Next step

`pixi run launch` to reload the dashboard; `kb-history` to see the merge.
