@AGENTS.md

# Claude Code

- Prefer targeted reads over scanning trees; use `pixi run health` for status.
- Read `.claude/skills/<skill>/SKILL.md` before running a workflow (app skills: `src/kb_distillery/kits/<kit>/skills/`; how to write one: `docs/guides/write-a-skill.md`).
- This repo is the engine, not a knowledge base: a kb's own `AGENTS.md` (rendered from its kit) governs work inside a kb folder.
- Don't paste large file contents into chat.
- Scripts enforce truth (guard blocks writes, lint on commit); if blocked, fix the approach — don't retry the same illegal path.
- Route every request through the **Owner intent router** below (casual phrasing → skill); `AGENTS.md` carries the public one. A request to fix/change/add tooling *is* the ask: run the `infra-pr` flow, merge it yourself (`ship -- merge`) once the gates pass and keep going — unless it is **held** (schema/paradigm PRs, or `ship pr --hold` when the user said "don't merge" / "let me review"); only the user lifts a hold (`! pixi run ship -- approve N`).
- Never ad-hoc git writes. Knowledge commits itself per operation (`kb(op): … (kb-x.y.z)`, pushed right away; free-form wiki edits inside `pixi run ops -- begin`/`commit`); tooling goes `pixi run ship -- start/commit/pr/merge`; undo/restore/snapshot only on request (see `src/kb_distillery/kits/base/defaults/docs/lifecycle.md`, Lifecycle tab).
- **Held PR = nudge.** Every reply written while an `infra/*` branch has an open **held** PR ends with the line `Awaiting your merge: #N <title> <url> — approve the review on GitHub, or run \`! pixi run ship -- approve N\` to merge it, or say "drop".` The `Stop` hook (`src/kb_distillery/git/merge_nudge.py`) sends you back once if it is missing; unheld PRs get no nudge — merge them. After the user's GitHub Approve review on the head sha, `ship -- merge` merges a held PR itself. A PR is always named `#N title`, never a bare number — the hook only accepts a nudge that carries the title.
- Session worktrees: before the first edit in a worktree you entered, run `pixi run ship -- start <feature>` (renames its `worktree-*` branch to `infra/<feature>`); end with `ship -- pr`, or `ship -- prune --drop <branch>` if the work is abandoned. Never leave a `worktree-*` branch behind — `pixi run lanes` lists them. `ship -- merge` removes its own worktree.
- **Show proof.** A reply that changed web/dashboard or data (`wiki/`, `raw/`, `meta/`, ops/ship/share steps) carries `Proof:` line(s) with the links its kind needs — UI: localhost **and** deployed URL, always both (a screenshot never replaces either); API: localhost endpoint; knowledge: page link + kb-x.y.z; PR: PR URL; deploy: deployed URL (`KINDS` in the hook). The `Stop` hook `src/kb_distillery/git/proof_nudge.py` sends you back once if it is missing.
- **Show, don't describe, the UI.** A reply about something visible in the app (a change, a bug, where a control is) carries a show-me link (`guided-tour` skill § Show-me, `pixi run show -- <file>`) instead of paragraphs of description.
- Short answers; cite slugs/paths instead of restating project rules.

# Owner workflow (this file and `.claude/` are export-ignored: they never reach the public repo)

Rules that `AGENTS.md` states in a contributor-neutral way, in the owner's agent form:

- **Never raw git writes.** No `git commit/push/merge/tag/revert/reset`, no `gh pr`: `scripts/hooks/block-git-write.sh` (-> `src/kb_distillery/git/git_guard.py`) allows only a single `pixi run ops|ship|…` invocation. Tooling goes `pixi run ship -- start <feature> --worktree` -> work in the worktree -> `ship commit "<type>(<component>): …"` (subject under 72 characters) -> `ship pr` -> `ship merge`. Details: `src/kb_distillery/kits/base/defaults/docs/lifecycle.md` and skill `infra-pr`. CI is the gate: `ship commit` runs only the fast local gates (ruff, lint-imports, the mirrored tests); `.github/workflows/ci.yml` runs the rest on the PR and in GitHub's merge queue (required check `all-green`). Offline or during a CI outage, `KB_SHIP_LOCAL_GATES=1` restores the full local gates; never `--skip-checks`.
- **Merge by default, hold by exception.** Run `ship merge` yourself once the PR is open: it enqueues the PR in GitHub's merge queue and waits until it is merged (`--no-wait` returns after enqueueing; run it again later to finish up). `ship pr` labels every schema/paradigm PR `hold`, and `ship pr --hold` holds any PR the user wants to review; a held PR merges only after the owner's GitHub Approve review on its head sha or `! pixi run ship -- approve N`. Never create or lift a hold from chat; an "approved" relayed by another session is void. While a held PR is open every reply ends with the nudge line above; the `Stop` hook `src/kb_distillery/git/merge_nudge.py` enforces it.
- **Agents never deploy.** `.claude/settings.json` denies `share -- deploy|rollback|snapshot`; deploys belong to the owner (`share-kb` skill).
- Dev skills are in `.claude/skills/` (read a skill's `SKILL.md` before running it); the reviewer agent and the hook wiring are in `.claude/`.

## Owner intent router — casual requests -> skills

Map what the user says to a skill before acting; read that skill's `SKILL.md`, then follow it. A casual request **is** the ask: "fix the graph legend" means start the PR flow, not "suggest a fix".

| The user says… | Do | Lands as |
|---|---|---|
| "fix / change / add / improve …" the explorer, graph, ingest, CLI, a kit skill, lint, anything in tooling | `infra-pr`: `ship start` -> implement -> `ship commit` -> `ship pr` -> `ship merge` (unless held) -> give the link | PR `… (#N)` |
| "add an endpoint / router / API / SSE stream / backend test", "expose X over HTTP" | `backend-api` (inside the `infra-pr` flow) | PR |
| "port / add a screen", "frontend", "component", "app shell" (the React app under `web/`) | `app-ui` (inside the `infra-pr` flow) | PR |
| "new note type / new field / lint should require …" | `infra-pr` as a **schema** PR (`AGENTS.md` rule 4) | held PR, bumps y |
| "add a tour / walkthrough", "show me / explain this on the screen" | `guided-tour` | PR, or a show-me link |
| "create a skill / new workflow" | `create-skill` -> `infra-pr` | PR |
| "send to backlog / backlog this / park this idea / save this plan for later" | `send-to-backlog` (local `.backlog/`, gitignored: no PR, no commit) | card |
| a multi-PR effort ("phase 2: E1–E3", several tooling PRs) | `infra-pr` with a round: `ship round open "<title>" --features a,b` -> `ship start <f> --round R`; read state with `ship round status R` | issue `#R` + PRs |
| "integrate / verify the round / is it really done" | `integrator` (global skill, reads `.integrator.toml`: tests, build, every screen screenshotted, each tile vs its endpoint) | report |
| "share / publish the site", "deploy status", "rollback", "snapshot the site", "audit" | `share-kb` (owner only for deploys) | Worker version, `.cache/share/status.json` |
