---
name: create-skill
description: >-
  Add or extend a meta/skills workflow skill with lint gate. Use for create skill,
  new skill, add skill workflow. Do NOT use for vault ingest, digest, or query.
---

# create-skill

**LLM tier:** none · **Budget:** 0 tokens

Meta-skill for authoring skills. Not part of the ingest/digest ladder.

## Triggers

- `create skill`, `new skill`, `add skill`, `skill template`

## Do NOT

- Use this to ingest papers or answer vault questions
- Skip `lint-skills` before `sync-skills`
- Add a top-level skill without README registration

## Decision tree

| Situation | Action |
|-----------|--------|
| Same pipeline, new trigger phrase | Extend existing skill `description` + `## Triggers` |
| New `raw/` type route | Add subskill under `scrap-data` or `ingest-to-catalog` |
| New LLM tier or workflow | New top-level skill + README ladder row |
| One-off task | No skill — handle in chat |

## Workflow

1. Copy [`SKILL_TEMPLATE.md`](SKILL_TEMPLATE.md) to `meta/skills/<name>/SKILL.md` (or subdir).
2. Fill frontmatter: `name` must match directory (`parent-child` for subskills).
3. Register in [`README.md`](README.md):
   - Ladder skill → row in **Token budgets** + **Skills** tables
   - Meta skill (like this one) → **Skills** table only, add to `META_SKILLS` in `lint_skills.py` if needed
4. Update [`AGENTS.md`](../../AGENTS.md) if triggers or ladder change.
5. Validate and sync:

```bash
pixi run lint-skills
pixi run test-skills
pixi run sync-skills
```

## Output

New or updated `meta/skills/**/SKILL.md`, README row, mirrored `.cursor/skills/`.

## Quality bar

- `pixi run lint-skills` → 0 errors
- Subskills listed in parent table when parent has child dirs with `SKILL.md`
- Bash blocks reference real CLI (`lint-skills` validates)

## Next step

Use the new skill's documented workflow; run `semantic-lint-hop` only after digest/distill skills.

## Commit

New or changed skills ship through `infra-pr` (an `infra/<feature>` PR), not on main. A skill that writes knowledge must end in an op commit (writer CLI or `ops begin`/`ops commit`).
