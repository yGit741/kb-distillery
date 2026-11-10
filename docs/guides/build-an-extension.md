# Build an extension

An extension is a separately installed Python package that adds a kit, a storage connector, a publisher or a skill to kb-distillery. The engine finds it through a Python entry-point group, so there is nothing to register by hand and no fork to maintain: `pip install my-extension` is enough.

Pick what you are adding:

| Adds | Entry-point group | Value points at | Detailed guide |
|---|---|---|---|
| A kit (page types, relations, skills, docs) | `kb_distillery.kits` | a package folder holding `kit.toml` | [Write a kit](write-a-kit.md) |
| A skill, on its own | `kb_distillery.skills` | a package folder holding `SKILL.md` | [Write a skill](write-a-skill.md) |
| A storage connector | `kb_distillery.storage.connectors` | a `Connector` subclass | [Add a storage connector](add-a-storage-connector.md) |
| A publisher | `kb.publishers` | a `Publisher` subclass | [Add a publisher](add-a-publisher.md) |

One package may register in several groups.

## Rules that hold for every group

- A built-in name always wins. A package cannot replace `base`, `research`, `local-folder`, `gdrive`, `none`, `cloudflare` or a skill the engine ships.
- A broken extension is skipped (a kit or skill folder without its marker file, a module that cannot be found), so one bad package never breaks the others. Connectors and publishers report a load error when a kb selects them.
- The engine does not run your package to discover it. Kits and skills are located without importing more than the package itself, so keep `__init__.py` light.
- Extensions are code or content a kb trusts. Install only what you trust, as with any Python package.

## A kit as a package

```
my-recipes/
  pyproject.toml
  src/my_recipes/
    __init__.py
    kit/
      __init__.py
      kit.toml            # [kit] name = "recipes", version = 1, extends = "base", [types] ...
      skills  (one folder per skill, each with a SKILL.md)
      defaults/docs/      # optional: docs, page skeletons, flags, as in a built-in kit
      views/*.toml        # optional: ready graph views
```

```toml
# pyproject.toml
[project]
name = "my-recipes"
version = "0.1.0"

[project.entry-points."kb_distillery.kits"]
recipes = "my_recipes.kit"

[tool.setuptools.package-data]
my_recipes = ["kit/**/*"]       # ship kit.toml, skills and defaults in the wheel
```

The entry-point name is the kit name and must equal `name` in `kit.toml`. A kb then uses it as it would a built-in kit: `distill init --kit recipes`, or `[kb] kit = "recipes"` in `kb.toml`. The kit's own skills are copied into the kb with the rest (`distill init --refresh` re-syncs them). Write the `kit.toml` as described in [Write a kit](write-a-kit.md); `extends` may name a built-in kit or another installed one.

## A skill as a package

```
my-skills/
  pyproject.toml
  src/my_skills/
    __init__.py
    tidy_notes/
      __init__.py
      SKILL.md            # front matter with name, description, audience, mode
```

```toml
[project.entry-points."kb_distillery.skills"]
tidy-notes = "my_skills.tidy_notes"
```

An installed skill is copied into the `.claude/skills/` of every kb on `distill init` and `distill init --refresh`, whatever its kit. A skill a kit ships under the same name wins over the installed one. Follow [Write a skill](write-a-skill.md) for the front matter and the rules a skill must meet. `lint-skills` covers the skills in the engine's own tree, not installed ones, so check yours against that guide by hand.

## A storage connector or a publisher as a package

Subclass `kb_distillery.storage.Connector` or `kb_distillery.hosting.Publisher` and register the class:

```toml
[project.entry-points."kb_distillery.storage.connectors"]
my-store = "my_pkg.store:MyStore"

[project.entry-points."kb.publishers"]
my-host = "my_pkg.host:MyHost"
```

A kb selects them in `kb.toml` with `[storage] connector = "my-store"` and `[publish] publisher = "my-host"`. The interfaces are in [Add a storage connector](add-a-storage-connector.md) and [Add a publisher](add-a-publisher.md).

## Test it without installing

The engine reads each group through one function, so a test can stand in for an installed package: put a fixture package in a temp folder on `sys.path` and patch `kb_distillery.config.kit._entry_points` (kits and skills), `kb_distillery.storage.registry._entry_points` or `kb_distillery.hosting.registry._entry_points`. `tests/kits/test_entry_points.py` is a worked example, with no network and no `pip install`.

To try a real install, `pip install -e .` your package into the environment that runs `distill`, then check:

```
distill init --kit recipes --kb-id scratch      # for a kit
python -c "from importlib.metadata import entry_points; print(entry_points(group='kb_distillery.kits'))"
```

## Share it

List it in [Community extensions](../community-extensions.md) once it is published.
