# Write a skill

A skill is a folder `<name>/SKILL.md` that tells an agent how to run one workflow. Where it lives depends on who uses it:

| Folder | For | Reaches a knowledge base |
|--------|-----|--------------------------|
| `src/kb_distillery/kits/base/skills/` | the workflows every kb needs (ingest, digest, query, wiki edits, history) | yes, copied into the kb's `.claude/skills/` |
| `src/kb_distillery/kits/<kit>/skills/` | a kit's own workflows (`research`: `build-researcher-profile`) | yes, when the kb uses the kit |
| `.claude/skills/` | working on the engine itself; maintainer-only tooling, not shipped in the public export | no |

Each of these folders has a `README.md` with a **Token budgets** table (one row per ladder skill) and a **Skills** table (every
skill, linked); `pixi run lint-skills` keeps both in sync with the folders. Skills ship in the wheel with the kits
(`resource("kits/<kit>/skills")`); there is no top-level skills folder and no symlink.

Read `<skill>/SKILL.md` before running a workflow.

## Adding a skill

1. **Extend vs new**: prefer extending an existing skill in the folder you target over adding a near-duplicate (the maintainers' `create-skill` decision tree is private tooling and is not shipped).
2. Copy [`_TEMPLATE.md`](../../src/kb_distillery/kits/base/skills/_TEMPLATE.md) to `<skills folder>/<name>/SKILL.md`.
3. Required: YAML `name` + `description` (with Use for / Do NOT), `## Triggers`, `## Do NOT`, `**LLM tier:**`, real CLI in `bash` blocks.
4. Register it in that folder's `README.md` (Token budgets row for ladder skills; Skills table always).
5. Update the Intent router in `AGENTS.md` if triggers change, and the Skill ladder in `src/kb_distillery/kits/base/defaults/docs/workflows.md` if the ladder changes.
6. Gate:

```bash
pixi run lint-skills
```

**Commands in a skill.** An app skill (kit) calls the installed CLI: `distill ingest …`, `distill ops …`, `distill lint`,
`distill propose …`, never `pixi run` or a repo path, because a kb has no checkout. A command that has no `distill` form yet
(`python3 -m kb_distillery.search.query`, `…search.explore_raw`, `…search.semfind`, `…vault.coherence`, `…digest`,
`…publish.export`, `…distill propose|revise|apply|abort`) stays a `python3 -m` line until it gets one. `lint-skills` checks
every `bash` block against the real CLI.

**Vault guardrails** (any skill that touches data): `raw/` immutable (use CLI); `think/` human-only; open ingest session → no direct `wiki/` writes (`guard.py`); post-write → `distill lint`.

**Every writing skill ends in one op commit.** Writer CLIs commit automatically (`--no-commit` to skip); any other wiki edit is wrapped in `distill ops begin …` / `distill ops commit` (see `wiki-edit`). Skills never run git writes themselves.

**Digest rule:** bare `digest` → ask tier; never auto-pick `full-digest`.
