# Pre-approvals for phases 2-9

Approving the PR that adds `docs/plans/` approves the plan of every phase (the roadmap asks for one approval per
phase; this is that approval, once). Steps that are outward-facing or irreversible are NOT covered by it: they run
only if their line below is ticked in the merged copy of this file, and only the user edits this file.

- [x] **Phase 2-6** run unattended phase by phase (each ends with its `phase-N-done` tag). Schema PRs still wait for your `ship approve`.
- [x] **Phase 7 history audit**: run gitleaks and the kb-content scan and report. (Safe: read-only.)
- [x] **Phase 7 history**: strategy `fresh initial commit into a NEW public repo` (recommended; no force-push) | `rewrite` | `none` -> fresh initial commit into a NEW public repo
- [x] **Phase 8 publish**: repo name yGit741/kb-distillery, visibility public, remotes for the thesis kb and think: new PRIVATE repos (never the old monorepo URL).
- [ ] **Phase 9 switchover** (runs right after Phase 6): window ________; rollback = `share rollback` + `switch.sh --rollback`; archive (never delete) the old monorepo.

Until a line is ticked, the agent stops before that step and writes what it would have done.
