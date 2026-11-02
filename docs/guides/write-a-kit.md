# Write a kit

A kit is a folder `src/kb_distillery/kits/<name>/` with a `kit.toml`. Use it when a family of knowledge bases needs the same page types.

If you need a type for one knowledge base only, add it to that knowledge base's `kb.toml` instead. See [kb.toml](../reference/kb-toml.md).

## Steps

1. Pick a name. It must equal the folder name.
2. Write `kit.toml`. List every type the kit uses, once, in `order`, and give each layer a table. The example is the `base` kit with one source type (`recipe`) and one concept type (`technique`) added:

   ```toml
   [kit]
   name = "recipes"
   version = 1
   extends = "base"          # optional: the kit this one builds on
   description = "Recipes, techniques and ingredients."

   [types]
   order = ["topic", "idea", "question", "person", "series", "recipe", "article", "technique"]

   [types.source.recipe]
   label = "Recipe"
   prefix = "recipe-"

   [types.source.article]
   label = "Article"
   prefix = "article-"

   [types.collection.series]
   label = "Series"
   prefix = "series-"
   kind = "contents"          # member files listed in a Contents table

   [types.concept.topic]
   label = "Topic"
   prefix = "theme-"

   [types.concept.idea]
   label = "Idea"
   prefix = ""

   [types.concept.question]
   label = "Question"
   prefix = "q-"
   status = ["open", "partial", "resolved"]

   [types.concept.person]
   label = "Person"
   prefix = ""
   status = []

   [types.concept.technique]
   label = "Technique"
   prefix = "technique-"

   [edges]
   types = ["uses"]
   ```

3. Add `skills/` for workflows that belong to the kit. Each skill is a folder with a `SKILL.md`. See [Write a skill](write-a-skill.md).
4. Add `AGENTS.template.md` if the kit has agent rules of its own. Put `{{parent}}` where the parent kit's text goes.
5. Run the checks:

   ```bash
   pixi run pytest tests/vault/test_kit.py tests/vault/test_kit_contract.py
   pixi run lint-skills
   ```

6. Create a knowledge base from it: `pixi run distill init --kit recipes --kb-id kitchen --yes`. To try a kit outside the repository, copy the kits folder, add yours, and point `KB_KITS_DIR` at the copy.

## Rules

- A kit holds the page types and relations. It does not hold `areas` or `deprecated_areas`. Each area needs a topic page in the knowledge base, so areas belong to the knowledge base.
- `extends` must name a kit that exists, without a cycle. It layers the parent's skills, defaults and hooks. The child does not copy the parent's `[types]` or `[edges]`: its ontology is the tables in its own file, and `order` must list every type once. A missing layer table makes the loader fall back to defaults and fail with `[types] order must list every type once`.
- Any other top-level table is rejected until the engine gives it a meaning.
- Bump `version` when a knowledge base must notice the change.
- Another kits folder can be set with `KB_KITS_DIR`.

## Errors

- `[kb] kit = 'x' is not a known kit`: the name is not in the kits folder.
- `the kit sets … and kb.toml gives …`: a knowledge base restates a value with a different content. Change the kit or drop the line.
- `[kit] needs name = '<folder>' and a version`: the kit file is incomplete.

More: [kits.md](../../src/kb_distillery/kits/base/defaults/docs/kits.md)
