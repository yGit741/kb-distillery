# Phase 8 plan: Publish

Depends on: Phase 7. Unattended-safe: NO.

Make the engine public and tag the first release.

## PRs

1. Public remote for kb-distillery; private remotes (or none) for the thesis kb and think.
2. Tag `v0.1.0` with release notes.

## Billing

None.

## Done when

Public repo live, CI green on GitHub, a fresh clone passes `kbd doctor`.

## Approval gates

- Outward-facing and irreversible once public: runs only if its line in preapprovals.md is ticked.

## Findings from the code review (2026-10-31)

- Make the engine public only via the new repo from Phase 7. The thesis kb and think get NEW private remotes (never `yonatan-thesis-kb`), because today their only copy is local plus the pre-distillery tarball.
- The standing rule "no remotes before Phase 8" no longer holds (private `origin`, PRs #1-#4); read it as "no public remote, never the old kb URL".

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-8-done` with `ship tag`; every earlier test layer stays green.
