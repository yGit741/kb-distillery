# Roadmap plans: order and ownership

Order (not 2..9): **2 Templates -> 3 Connectors -> 4 Think -> 5 init/doctor -> 6 Sharing -> 9 Switchover -> 7 OSS readiness -> 8 Publish**.
Phase 9 moved up because it depends on Phase 6, not on going public.

Work the agent does alone: everything except the steps below. User-only steps (one at a time, with exact commands):
- `! pixi run ship -- approve N` for each held schema PR (PR C, then the Phase 2 spec; two sequential approvals) and for the plans PR.
- Flipping `graph-relations` in System -> Flags (needs the owner token).
- Cloudflare D1 token rotation, the first live deploy, the launchd switch, archiving the old repo (Phase 9).
- Phase 7 history strategy, Phase 8 going public, remotes for the thesis kb and think (see `preapprovals.md`).

Standing rules: `KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; `ship` pushes as the user's `gh` login (the GitHub App is not installed on this repo), and a GitHub Approve review does nothing here, only `ship approve N` lifts a hold.
