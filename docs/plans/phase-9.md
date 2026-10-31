# Phase 9 plan: Switchover from knowledge-base-thesis

Depends on: Phase 8 and Phase 6. Unattended-safe: NO.

Move the live setup off the old monorepo.

## PRs

1. launchd jobs and the Cloudflare deploy move to kb-distillery + the publisher plugin.
2. Archive (never delete) the old monorepo; lift the no-`kb(...)`-ops rule.

## Billing

None.

## Done when

The live site is served from the new setup; nothing runs from the old repo.

## Approval gates

- Touches the live site: runs only if its line in preapprovals.md is ticked, with a rollback plan.

## Findings from the code review (2026-10-31)

- Depends on Phase 6, not Phase 8: going public has nothing to do with serving the site. It runs right after Phase 6.
- Current state (2026-10-31): the launchd jobs `com.thesis-kb.daily-sync` and `com.thesis-kb.deploy-owner` were failing (their `cd` target does not exist) and are unloaded and disabled; the live site is frozen at its last Worker version. The old monorepo is intact at `backups/knowledge-base-thesis`.
- Steps: the agent writes `tools/launchd/*.plist` and `switch.sh` with a `--rollback` option and dry-runs it; the user rotates the Cloudflare D1 API token (dashboard) and runs `bash tools/launchd/switch.sh`; the agent runs `pixi run share -- deploy-main --dry-run`, the user runs the real deploy; rollback = `share rollback` + `switch.sh --rollback`; the old repo is archived with `gh repo archive` (reversible with `unarchive`), never deleted.

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-9-done` with `ship tag`; every earlier test layer stays green.
