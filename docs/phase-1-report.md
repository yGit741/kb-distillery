# Phase 1 report: foundation, name, layout, git hygiene

Tag `phase-1-done` (engine, `5bd9410`). This report closes roadmap 1.6.

## What Phase 1 delivered
- **Layout:** the engine is `kb-distillery`; each knowledge base is its own git repo under `kbs/` (`kbs/demo` tracked,
  `kbs/yonatan-thesis` and `kbs/think` local). One discovery path: `kbs/<id>` or `--kb <path>` (`kbd kb-list`).
- **Tooling:** `ship tag`, `kbd`, Billing docs, kb hooks resolving the engine from `../..` (the thesis kb carries the
  matching `chore(hooks)` commit).
- **One door to Claude:** `kb.llm` with `subscription | api | batch` backends (#188).
- **Graph:** edge kinds read from the kb and Cypher queries over the page graph (#194), API and chat-agent hook.
- **Branches:** `main` only; one worktree; stale `infra/*` branches deleted.

## Verification
- **Tests, thesis kb** (`KB=yonatan-thesis pixi run test`): 1284 passed, 232 skipped (recorded run `v1b-thesis`).
- **Tests, demo kb:** 938 passed, 527 skipped, 1 failed (the vector-cache test for a kb inside the engine checkout,
  fixed by #196). The skips are tests that assume the thesis types or the monorepo layout; they are the Phase 2 and
  Phase 6 debt.
- **Dashboard tour, both kbs** (`--kb demo`, `--kb yonatan-thesis`): all nine screens of `.integrator.toml` (home,
  graph, system, system-flags, pages, chat, scopes, pipeline, lifecycle) loaded at 1440x900 with 0 page errors.
  18 screenshots are kept locally in `~/local-workspace-personal/backups/phase1-tour-full/`; they are not committed
  because the thesis ones show kb content.

## Waivers and findings
- **"knowledge-base-thesis untouched" (1.6) passes.** The old folder was briefly moved to the Trash at the owner's
  request (2026-10-30) and restored by the owner to `~/local-workspace-personal/backups/knowledge-base-thesis`. Checked
  2026-10-31: HEAD `9b74d91` (kb-1.3.14), `main` equals `origin/main`, only the same three untracked Think files, 3789 raw
  files. Before the move its `raw/`, `wiki/`, tracked `meta/` and Think notes were also compared with
  `kbs/yonatan-thesis` and `kbs/think` and were identical. `backups/pre-distillery-20261030.tgz` and the raw manifest remain.
- **Live jobs.** `com.thesis-kb.daily-sync` and `com.thesis-kb.deploy-owner` were failing (their `cd` target
  `~/local-workspace/personal-knowledge-base` does not exist; deploy-owner was in a respawn loop). They were unloaded and
  disabled on 2026-10-31. The live site is frozen at its last deployed version until the switchover phase.
- **Remotes.** The "no remotes before Phase 8" rule no longer holds: `origin` is the private
  `yGit741/kb-distillery`. The thesis kb has no remote and must never be pushed to the old monorepo URL.
- **Gate baseline.** `ship` pushes as the user's own `gh` login: the GitHub App is not installed on the new repo.
