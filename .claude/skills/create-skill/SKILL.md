---
name: create-skill
description: >-
  Add or extend a skills workflow skill with lint gate. Use for create skill,
  new skill, add skill workflow. Do NOT use for vault ingest, digest, or query.
audience: dev
mode: write
---

# create-skill

**LLM tier:** none · **Budget:** 0 tokens

Meta-skill for authoring skills. Not part of the ingest/digest ladder.

## Triggers

- `create skill`, `new skill`, `add skill`, `skill template`

## Do NOT

- Use this to ingest papers or answer vault questions
- Skip `lint-skills`
- Add a top-level skill without README registration

## Decision tree

| Situation | Action |
|-----------|--------|
| Same pipeline, new trigger phrase | Extend existing skill `description` + `## Triggers` |
| New `raw/` type route | Add subskill under `scrap-data` or `ingest-to-catalog` (`src/kb_distillery/kits/base/skills/`) |
| New LLM tier or workflow | New top-level skill + README ladder row |
| One-off task | No skill — handle in chat |

## Workflow

1. Pick the folder: a workflow every kb needs → `src/kb_distillery/kits/base/skills/`; one kit's own → `src/kb_distillery/kits/<kit>/skills/`; working on the engine itself → `.claude/skills/`. Guide: [`docs/guides/write-a-skill.md`](../../../docs/guides/write-a-skill.md).
   Copy [`_TEMPLATE.md`](../../../src/kb_distillery/kits/base/skills/_TEMPLATE.md) to `<folder>/<name>/SKILL.md` (or subdir). App skills call `distill …`, not `pixi run`.
2. Fill frontmatter: `name` must match directory (`parent-child` for subskills); `audience: app` (kit skills) or `dev` (`.claude/skills`); `mode: read` (never changes a file) or `write`. An app skill never mentions ship/PRs; a read skill never names Write/Edit.
3. Register in that folder's `README.md`:
   - Ladder skill → row in **Token budgets** + **Skills** tables
   - Meta skill (like this one) → **Skills** table only, add to `META_SKILLS` in `src/kb_distillery/lint/lint_skills.py` if needed
4. Update the Intent router in [`AGENTS.md`](../../AGENTS.md) (public) and the Owner intent router in [`CLAUDE.md`](../../CLAUDE.md) (dev skills) if triggers change, and the Skill ladder in [`src/kb_distillery/kits/base/defaults/docs/workflows.md`](../../src/kb_distillery/kits/base/defaults/docs/workflows.md) if the ladder changes.
5. Validate:

```bash
pixi run lint-skills
pixi run test-skills
```

## Writing the description

The `description` is the only text the agent sees when choosing a skill, so it decides whether the skill fires. `lint-skills` warns when it lacks a `Use` trigger or a `Do NOT` clause.

1. **Forceful trigger line** — `Use for <phrase>, <phrase>, <phrase>.` Name the exact words the user says, in their casual form, not an abstract category.
2. **Explicit near-misses** — `Do NOT use for <neighbour case> (use <other-skill>).` Name the closest sibling skills and the requests most likely to be confused with this one.
3. Keep it 20-500 characters; put detail in the body (`## Triggers`, `## Do NOT`), not the description.

Before registering, write 4 prompts that should trigger and 4 that should not, and check each against the description. Example for `export-kb`:

| Should trigger | Should NOT trigger |
|----------------|--------------------|
| "export kb" | "share the site" (`share-kb`) |
| "zip the wiki for ChatGPT" | "snapshot the KB" (`kb-snapshot`) |
| "share kb with an external LLM" | "what do I know about tensor rank" (`query-knowledge`) |
| "make a text bundle of wiki and think" | "deploy main" (`share-kb`) |

## Output

New or updated `<folder>/**/SKILL.md` and its folder's README row. A kit skill reaches a kb through `distill init` (C.4), so there is nothing to copy by hand.

## Quality bar

- `pixi run lint-skills` → 0 errors
- Subskills listed in parent table when parent has child dirs with `SKILL.md`
- Bash blocks reference real CLI (`lint-skills` validates)

## Next step

Use the new skill's documented workflow; run `semantic-lint-hop` only after digest/distill skills.

## Commit

New or changed skills ship through `infra-pr` (an `infra/<feature>` PR), not on main. A skill that writes knowledge must end in an op commit (writer CLI or `ops begin`/`ops commit`).
