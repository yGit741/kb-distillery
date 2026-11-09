---
name: infra-pr
description: >-
  Fix, change or add tooling (dashboard, explorer, graph, ingest CLI, skills, lint, schema) via an
  infra/<feature> branch and a GitHub PR merged as "(#N)". Use for fix the …, change the …, add a feature,
  bug in the dashboard or pipeline, ship, open PR, merge PR, schema change. Do NOT use for knowledge
  edits in wiki/ (use wiki-edit). Merges its own PRs unless held (schema/paradigm or the user asked to review).
audience: dev
mode: write
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
- Pipe `ship` through `| tail` hoping to catch a failure: every `commit`, `pr`, `merge` and `sync` ends with one `RESULT: ok|FAILED (...)` line, and a local gate's full output is in `.cache/ship-gates/*.log` (a failing gate also prints its last 25 lines). Read a log or a big file with an offset and a limit, never whole: it stays in the conversation and is re-read on every later turn
- Run `git commit` / `git push` / `gh pr` directly — blocked; `pixi run ship` is the path

## CLI

```bash
pixi run ship -- start graph-legend --worktree
pixi run ship -- commit "feat(dashboard): graph legend redesign"
pixi run ship -- review --pass "reviewer: no blockers"   # after the reviewer subagent; pr refuses without it
pixi run ship -- pr --title "feat(dashboard): graph legend redesign"
pixi run ship -- pr --hold                      # the user wants to review it
pixi run ship -- merge
pixi run ship -- merge --no-wait                # enqueue and return; run merge again later to finish up
pixi run ship -- night start --until 07:00     # overnight: no holds, CI decides (expires by itself)
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
2. Commit with `ship -- commit "type(component): imperative summary"` — types by what changed: `schema` (note rules) › `feat` (new capability) › `fix` (wrong behaviour) › `chore` (no behaviour change: config, docs, tests, refactors); scope is a component (`vault raw books think ingest lint guard dashboard skills distill query export scrap git obsidian claude gemini`). Refusals that need no gate (bad message, nothing to commit, unrelated files already staged) come first and cost nothing. Then only the fast local gates run (no gate slot, no load wait, target under two minutes): ruff, lint-imports (the layer contract), pytest with `-n auto` on the test dirs mirroring the touched `src/kb_distillery/<pkg>`, the changed test files and always the top-level `tests/test_*.py` invariants (`.github/` maps to `tests/ci`, `.claude/skills/` to `tests/lint`, `docs/*.md` and top-level `*.md` to nothing; config (`pixi.toml`, `pyproject.toml`, `conftest.py`) or anything unmapped runs the full suite), and `web-typecheck` when `web/` changed. CI runs everything else. Only the paths present before the gates are committed, minus generated files. Untracked raw PDFs are linked from the primary checkout automatically.
3. **Review first:** spawn the read-only `reviewer` subagent (`.claude/agents/reviewer.md`) on the branch and fix its blocking findings, commit, then record the pass with `ship -- review --pass "<one-line summary>"` (`--findings N` optional; it pins HEAD, so a later commit needs a fresh review; the summary lands in the PR body under `## Review`; `--no-review "<reason>"` on `pr` is the escape hatch). Then `ship -- pr`, which refuses without a pass for HEAD. It pushes and opens the PR; it does not run the full gates or the lane checks (CI does: `.github/workflows/ci.yml`, required check `all-green`). `--skip-checks` only matters under `KB_SHIP_LOCAL_GATES=1`.
   `KB_SHIP_LOCAL_GATES=1` restores the old local behaviour in every step (full suite and lane checks at commit, pr, sync --continue and merge) for offline work or a CI outage. In that mode a gate that already passed on exactly this content prints `gate: <name> reused (<sha7>)` instead of running (records in `.cache/ship-gates/reuse/`; a `commit` subset pass is never reused), and only one gate run at a time takes the machine-wide `kb-gate.lock` (`gate slot: waiting for <branch> (pid …)`, gives up after `KB_GATE_WAIT`, default 45 min); let it wait, do not poll machine load or run gates by hand to dodge the queue.
   `ship -- pr` pushes and opens the PR (idempotent). Pass `--title` when the branch has several commits — its type must be the highest of them (paradigm › schema › feat › fix › chore) and the whole `<title> (#N)` must fit 100 chars; `ship` refuses otherwise. Add `--hold` when the user wants to review it; schema/paradigm PRs get the `hold` label automatically.
4. **Not held → merge it yourself:** `ship -- merge` → enqueues the PR in GitHub's merge queue (`gh pr merge --merge --auto`; the queue tests the real merge result, no local sync) and watches it every 30 s until merged (up to `KB_MERGE_WATCH`, default 60 min; Ctrl-C is safe; `--no-wait` returns after enqueueing and a later `ship -- merge` finishes up), merged as `<title> (#N)`; then it fast-forwards the primary checkout and removes the worktree and local branch. A red required check, a PR that left the queue or a moved approved head exits 1 with the reason: fix it with a new commit and `ship -- pr`, then `ship -- merge` again; on a conflict run `ship -- sync` (continue in the primary checkout — its path is printed). Report the merged PR as `#N title`. **Held →** stop; `ship merge` refuses until the user approves: a GitHub **Approve** review by the owner on the current head sha (phone app works; then `ship -- merge` lifts the hold and merges; new commits → "re-approve") or `! pixi run ship -- approve N` (agents are blocked from `approve`, `gh pr review` and editing labels). `ship -- status` shows each held PR as `approved ✓ (sha ok)` / `approved on old sha` / `awaiting review`. Until then **end every reply** with `Awaiting your merge: #N <title> <url> — approve the review on GitHub, or run \`! pixi run ship -- approve N\` to merge it, or say "drop".` (the `Stop` hook `src/kb_distillery/git/merge_nudge.py` enforces it once per reply). `pixi run lanes` shows anything left behind; `ship -- prune --apply` clears merged clean worktrees.
5. **Feature flag:** a feature that can't land in one PR ships dark behind a new `[[flag]]` in `src/kb_distillery/kits/base/defaults/flags.toml` (needs `owner`, `expires` ≤ 90 days after `created`) and merges in small PRs; add tests for **both** states (`@pytest.mark.flag(name, True|False)` / `withFlag(name, true|false, …)` — `flags-check` fails otherwise); release = flipping the flag, not deploying. Expired flags are a lint error — remove them with `src/kb_distillery/kits/base/defaults/templates/flag-cleanup-pr.md`.
6. **Schema PR:** bump `SCHEMA_VERSION` in `src/kb_distillery/vault/schema.py`, add `src/kb_distillery/migrations/NNNN_<name>.py` (`PRODUCES`, idempotent `apply(root)`), run `pixi run ops -- migrate` on the branch, commit as `schema(<scope>): …`. `ship -- merge` snapshots the current version (`pre-<feature>`), writes `KB-Version: x.(y+1).0` as the last line of the PR body (the queue's merge commit carries it) and tags it as the new baseline (`post-<feature>`). A **paradigm** PR (`paradigm(<scope>): …`, e.g. schema 1.0, the source model) works the same way but bumps x: `(x+1).0.0`.

## Output

A merge commit on main `type(scope): summary (#N)`; tooling is unversioned, schema/paradigm merges bump the knowledge version.

## Next step

`pixi run launch` to reload the dashboard; `kb-history` to see the merge.
