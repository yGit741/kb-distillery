# Phase 3 plan: Storage connectors

Depends on: Phase 2. Unattended-safe: yes.

Raw sources are reached through a connector interface, so a kb's inputs can live in a local folder (default), Google Drive or a third-party package.

## PRs

1. `kb.storage` interface (`list/get/put/info/local_copy/auth`) + a contract test suite.
2. Built-in local-folder connector (default).
3. Move the ~43 raw-access modules onto it in 3-4 batches by area (ingest, lint/corpus, search, share).
4. Google Drive connector.
5. Third-party connectors via package entry points, proven with a dummy package.
6. Lint rule: no module touches `raw/` directly.

## Billing

None.

## Done when

No module touches `raw/` directly (lint test); the thesis kb behaves as before.

## Approval gates

- None beyond this plan's approval.

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-3-done` with `ship tag`; every earlier test layer stays green.
