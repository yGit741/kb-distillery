# Phase 6 plan: Decouple sharing

Depends on: Phase 5. Unattended-safe: yes (the live site is untouched).

Publishing is a plugin outside core. Cloudflare becomes the first publisher, off by default.

## PRs

1. Publisher interface (`kb.publish`) outside core.
2. Remove the 8 core imports of `kb.share` (metrics/d1, dashboard/serve, api/routers/share, api/spa, ops/core, ops/nightly_report, ops/hygiene, services/ops).
3. Cloudflare publisher plugin, off by default; `KB_SHARE_AUTODEPLOY=0` stays.

## Billing

None.

## Done when

Core runs and all tests pass with no publisher installed.

## Approval gates

- None beyond this plan's approval.

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-6-done` with `ship tag`; every earlier test layer stays green.
