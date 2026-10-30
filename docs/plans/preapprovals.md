# Pre-approvals for phases 2-9

Approving the PR that adds `docs/plans/` approves the plan of every phase (the roadmap asks for one approval per
phase; this is that approval, once). Steps that are outward-facing or irreversible are NOT covered by it: they run
only if their line below is ticked in the merged copy of this file, and only the user edits this file.

- [ ] **Phase 2-6** run unattended phase by phase (each ends with its `phase-N-done` tag).
- [ ] **Phase 7 history audit**: run gitleaks and the kb-content scan and report. (Safe: read-only.)
- [ ] **Phase 7 history rewrite**: allowed strategy: `rewrite` | `fresh initial commit` | `none` -> ________
- [ ] **Phase 8 publish**: repo name ________, visibility ________, remotes for the thesis kb and think ________.
- [ ] **Phase 9 switchover**: window ________, rollback plan ________, archive (never delete) the old monorepo.

Until a line is ticked, the agent stops before that step and writes what it would have done.
