# Ontology kits

A kit is the schema a knowledge base follows: its page types, areas, source fields and typed edges. It is versioned in the engine (`src/kb_distillery/kits/<name>/kit.toml`, package data, so it ships in the wheel too); a kb names one and may extend it, never edit it. Two kits ship: `base` (a small general kb) and `research` (academic research; `extends = "base"`). The base kit's `defaults/` folder beside its `kit.toml` holds what every kb falls back to: flags, routed docs, page skeletons, digest instructions. Code: `src/kb_distillery/config/kit.py`. Tests: `tests/config/test_kit.py`, `tests/config/test_kit_contract.py`.

## A kb names its kit

```toml
# <kb folder>/kb.toml
[kb]
id = "my-kb"
name = "My knowledge base"
schema_version = "1.4"
kit = "research"      # optional; without it the kb.toml carries its own [types] / [edges]
```

`distill init` writes `kit`. The older key `template` is still read, and the old kit names `starter` and `academic-research` resolve to `base` and `research`, so a kb.toml written before the rename keeps working. Naming two different kits (`kit` and `template`) is refused.

`[types]` and `[edges]` in that kb.toml then **extend** the kit's:

| Value | Rule |
|---|---|
| a table (`[types.source.paper]`, `[edges]`) | merged key by key |
| a list (`areas`, `types`, `symmetric`, `note_required`, `order`) | unioned, the kit's entries first |
| a value the kit already sets | must be equal; otherwise the engine refuses with `[types].source.paper.label: the kit sets 'Paper' and kb.toml gives 'Article'` |

So a kb can add a type, an area or an edge type, and can restate what the kit says, but cannot rename, recolour or remove anything the kit defines. To change the kit, change the kit (a PR on `src/kb_distillery/kits/<name>/`).

The merge is in `KbConfig.section`, so every reader (`kb_distillery.vault.kbtypes`, `kb_distillery.graph.model.edge_config`) sees the same result, whatever imports first.

## The file

```toml
[kit]
name = "research"             # must equal the folder name
version = 1                   # bump when a kb must notice the change
extends = "base"              # optional: the kit this one builds on (must exist, no cycle)
description = "..."

[types]    # the kb.toml [types] format, see src/kb_distillery/vault/kbtypes.py
[edges]    # types, symmetric, note_required, labels: see src/kb_distillery/graph/model.py (edge_config)
```

`extends` is checked when a kb loads, and later steps use it to layer a kit's resources (defaults, skills, hooks) over its parent's. It does not copy the parent's `[types]` / `[edges]` into the child: a kit's ontology is exactly the tables in its own `kit.toml` (so a kb naming `research` gets research's types and colours, not base's).

**Areas are the kb's, not the kit's.** `areas` and `deprecated_areas` (the `area:` whitelist) stay out of a kit: every area needs its own `theme-<area>` topic page, so a kit that listed some would make lint fail for every kb that follows it. A kb adds them under its own `[types]`.

**Chat agent skills** sit in `[agent] skills` (`kb_distillery.services.agent_skills`): the app skills the chat agent may use in agent mode; `base` lists `deep-research`. A kb.toml `[agent] skills` replaces the kit's list (`[]` turns skills off). A name only counts when the skill exists in the kit chain with `audience: app` and `mode: read`.

**Page conventions** sit in `[pages]` (`kb_distillery.config.pages`): `takeaways_heading` (the `## <heading>` where a source page says what it means for the reader; engine default `Takeaways`) and `focus_slugs` (convention pages kept out of retrieval and orphan checks; default none). A kb.toml `[pages]` wins over its kit chain, the kit itself over the kits it extends. `research` keeps the generic `Takeaways` and sets `["focus"]` as its focus page. A kb centred on one project overrides both in its own kb.toml, e.g. `[pages] takeaways_heading = "Takeaways for my thesis"` and `focus_slugs = ["thesis"]`. A kb whose pages carry another heading renames them with `distill kb takeaways` (dry run; `--apply` writes). Source templates write the heading as `## {{takeaways_heading}}`; the engine fills it from this setting when it creates a page (`vault.frontmatter.fill_conventions`), so write the kb heading when copying a template by hand.

Any other top-level table is rejected until a phase gives it a meaning. Reserved: lint rules, migrations, samples. Page skeletons live in `src/kb_distillery/kits/base/defaults/templates/*.md`; a kit that extends another carries only the skeletons it changes in its own `defaults/templates/` (`research` does), found per file, the kit itself first.

## Ready views

A kit ships ready views in `kits/<name>/views/*.toml`: stacks of layers a person applies from `/views` in the graph. Each file holds `[[view]]` tables with `id`, `name`, `description` (one plain line) and `layers`, a one-line array where each entry is one line of the graph's query language (`web/src/features/graph/layers/grammar.ts`, e.g. `"show nodes degree >= 8"`, `"style nodes color by type"`; `favorites` stands for the pages marked as favorites). A kit that extends another adds its own views; the same `id` replaces the parent's. `kb_distillery.config.kit.views(name)` loads them, `GET /api/views/ready` serves them as text, and the frontend parses the lines; a line it cannot read shows the view as "cannot run on this kb". `web/src/features/graph/layers/readyViews.test.ts` parses every line of every kit.

## Where the kits are

`$KB_KITS_DIR` (tests, a second kits folder) or the package's own `kits/` (`resource("kits")` in `kb_distillery.config.resources`). The defaults the engine falls back to when a kb has no `meta/<x>` are `resource("kits/base/defaults")` (`kb_distillery.config.paths.META_DEFAULTS_PATH`).

## Errors you will meet

- `[kb] kit = 'x' is not a known kit (known: …)`: raised when kb.toml loads (the same for the older `template`); the kits dir is `$KB_KITS_DIR` or `src/kb_distillery/kits`.
- `…: the kit sets … and kb.toml gives …`: an edit; move it into the kit or drop it.
- `[kit] needs name = '<folder>' and a version`: the kit file is malformed. `extends = 'x' is not a known kit` / `extends itself`: fix the parent name or the cycle.
