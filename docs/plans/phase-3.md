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

## Findings from the code review (2026-10-31)

- The raw-access footprint is 19 modules using `RAW_PATH`/`RAW_DIR` and 66 files matching a broad raw/corpus pattern (25 in `ingest/`, 4 in `migrations/`, which is exempt), not "~43". Start the lint rule in report-only mode; its output replaces the guess.
- Connector keys are LOGICAL paths (`raw/...`), because wiki pages cite raw paths literally. `info()` returns the sha1 that `meta/corpus.tsv` already stores; `meta/raw-renames.tsv` semantics stay as they are.
- The Google Drive connector reads the macOS Drive mount (`~/Library/CloudStorage/GoogleDrive-*`, see `ingest/gdrive.py`); no OAuth is needed. Contract tests use a temp directory standing in for the mount. An API/OAuth variant would need a Google Cloud client (user) and is left for later.
- The idea of one content-addressed central raw store with per-kb manifests is NOT in this phase (it would break "behaves as before" and the path citations). Fixing the key shape here makes it a later connector with no engine change (post-v0.1).

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-3-done` with `ship tag`; every earlier test layer stays green.
