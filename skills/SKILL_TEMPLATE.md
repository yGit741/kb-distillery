---
name: your-skill-slug
description: >-
  One-line purpose. Use for <explicit triggers>. Do NOT use for <anti-triggers>.
---

# your-skill-slug

**LLM tier:** none | light | medium | heavy · **Budget:** 0 | ~2–4k | ~8–12k | ~25–40k+ tokens

<!-- Replace tier and budget to match skills/README.md ladder row. -->

## Triggers

- `your-skill-slug`, `alternate trigger phrase`

## Do NOT

- Anti-triggers that must not invoke this skill
- Vault violations (e.g. direct writes to `raw/`, `think/`)

## CLI

```bash
python3 meta/your_script.py
pixi run your-task
```

<!-- Only reference commands that exist in meta/ or pixi.toml. lint-skills validates bash blocks. -->

## Agent steps

1. Step one
2. Step two
3. Run `python3 -m kb.lint.lint` after vault writes

## Output

What changes in the vault (`wiki/` pages by layer — source, collection, concept — `corpus.tsv`, etc.).

## Quality bar

When this skill is considered complete.

## Next step

Handoff to the next skill in the ladder (e.g. `full-digest` → `semantic-lint-hop`).

---

**Registration checklist**

- [ ] Row in `skills/README.md` (Token budgets + Skills tables)
- [ ] `AGENTS.md` Intent router if triggers change; `meta-defaults/docs/workflows.md` Skill ladder if the ladder changes
- [ ] `pixi run lint-skills`
- [ ] `pixi run sync-skills`
