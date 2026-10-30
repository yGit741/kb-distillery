# Phase 7 plan: Open-source readiness

Depends on: Phase 6. Unattended-safe: audit, docs and CI yes; a history rewrite NO.

Make the repo safe and understandable for a stranger.

## PRs

1. History audit: gitleaks plus a scan for kb content, personal paths and secrets (known: `.vscode/settings.json`, one test file and 5 commits mention a personal path or employer).
2. Docs: README quick start, ARCHITECTURE, CONTRIBUTING, template- and connector-author guides, LICENSE (MIT).
3. CI: tests, lint, privacy check, UI tour on demo.
4. Name check on GitHub and PyPI.

## Billing

None.

## Done when

A stranger following only the README succeeds (fresh clone in a temp dir).

## Approval gates

- Rewriting history or starting from a fresh initial commit needs your pre-approval (see preapprovals.md).

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-7-done` with `ship tag`; every earlier test layer stays green.
