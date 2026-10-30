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

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-9-done` with `ship tag`; every earlier test layer stays green.
