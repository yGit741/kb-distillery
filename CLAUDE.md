@AGENTS.md

# Claude Code

- Prefer targeted reads over scanning trees; use `python3 -m meta.dashboard` or `meta/lint.py --health` for status.
- Read `meta/skills/<skill>/SKILL.md` before running a workflow (see `meta/skills/README.md`).
- One transactional workflow at a time; don't paste large file contents into chat.
- Scripts enforce truth (guard blocks writes, lint on commit); if blocked, fix the approach — don't retry the same illegal path.
- Route every request through the **Intent router** in `AGENTS.md` (casual phrasing → skill). A request to fix/change/add tooling *is* the ask: run the `infra-pr` flow and return the PR link; merge only when the user says merge.
- Never ad-hoc git writes. Knowledge commits itself per operation (`kb(op): … (kb-x.y.z)`; free-form wiki edits inside `pixi run ops -- begin`/`commit`); tooling goes `pixi run ship -- start/commit/pr/merge`; undo/restore/snapshot only on request (see `.cursor/rules/git.mdc`, Lifecycle tab).
- Bare **"digest"** → ask tier (easy / full / deep). Never auto-run `full-digest` or `deep-digest`.
- Short answers; cite slugs/paths instead of restating project rules.
