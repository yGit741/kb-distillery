# Phase 7 history and privacy audit (read-only)

Run 2026-10-31 on `main` of the engine repo (`kb-distillery`), read-only: no history was rewritten and nothing was pushed. `gitleaks` is not installed, so the scan is the repo's own (`python -m kb.lint.privacy`, patterns below). Install gitleaks into the pixi env before publishing and rerun; this report is the floor, not the proof.

## What was scanned

- **Patterns, personal:** the owner's local path and handles, the private site's host, the old monorepo name. **Patterns, secrets:** Anthropic, AWS, GitHub, Slack and Google API key shapes, private-key headers.
- **Tracked files** (`kbs/` skipped: knowledge is never in this repo) and **all history** (`git log --all`).

## Findings

_Update: the first run counted 27 files because it also matched Cloudflare's generic `workers.dev` domain. The owner's site is caught by its name, so the pattern was narrowed and the count is 23._

| Area | Result |
|---|---|
| Tracked files naming the owner, a local path or the private host | **23 files** (listed in `backend/tests/lint/privacy_baseline.txt`). Mostly share/deploy code and tests (the private host name), flags metadata (owner), and a few docs. |
| Token-shaped strings in tracked files | **2 files**, both test fixtures with fake, truncated keys (`backend/tests/ingest/test_chat_kb.py`, `frontend/src/features/chat/ChatScreen.test.tsx`). No real secret found. |
| Token-shaped strings in history | **11 added lines in 2 commits' files, the same two test files.** None elsewhere. |
| Commits adding a personal string | **25 commits** (`git log --all -G<personal patterns>`). |
| Tracked paths that must not be public | `.vscode/settings.json` (tracked, carries a personal path). `_quarantine/`, `.backlog/` and `kbs/yonatan-*`, `kbs/think` are not tracked. |
| Author identities in history | 429 commits by the owner's personal email, 138 by a GitHub noreply address, 41 by the knowledge-base bot, 10 other noreply. |

## What this means for publishing

- **No real secret was found**, but the history carries the owner's personal email on 429 commits and personal paths in 25 commits. That settles the strategy you chose: **a fresh initial commit in a new public repo**, authored with the noreply address. A history rewrite is not needed, and the private `yGit741/kb-distillery` stays as the archive of PRs and history.
- Before the fresh commit: empty or justify every line of the baseline (23 files), untrack `.vscode/settings.json`, and rename or parameterize the private host name where it is hard-coded (`share/`, `backend/src/kb/share/`, tests and skills). The privacy ratchet (`backend/tests/lint/test_privacy_ratchet.py`) stops the list from growing meanwhile.
- **Not covered by this scan, check by hand:** the launchd plists (they reference a corporate CA file path, per the plan), Cloudflare/D1 account ids in logs, and binary files. Add gitleaks and trufflehog to CI in the Phase 7 CI PR.

## Next

1. Phase 7 CI PR: run `kb.lint.privacy` and gitleaks on every push, fail on a file outside the baseline.
2. A clean-up PR per baseline group (share host name, tests, docs), each shrinking the baseline.
3. The fresh-commit step itself needs your go: it creates the public repo (`preapprovals.md`, Phase 8).
