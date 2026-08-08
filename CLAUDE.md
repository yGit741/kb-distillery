@AGENTS.md

# Claude Code

- Prefer targeted reads over scanning trees; use `python3 -m meta.dashboard` or `meta/lint.py --health` for status.
- Read `meta/skills/<skill>/SKILL.md` before running a workflow (see `meta/skills/README.md`).
- One transactional workflow at a time; don't paste large file contents into chat.
- Scripts enforce truth (guard blocks writes, lint on commit); if blocked, fix the approach — don't retry the same illegal path.
- Bare **"digest"** → ask tier (easy / full / deep). Never auto-run `full-digest` or `deep-digest`.
- Short answers; cite slugs/paths instead of restating project rules.
