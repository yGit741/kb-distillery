# 0002. Kits own the schema; a knowledge base extends and never edits

Status: accepted.

## Context

A knowledge base needs a schema: page types, filename prefixes, fields, typed relations. In the first version, each knowledge base carried its own schema in `kb.toml`. This made copies drift. A fix to the schema of one meant manual edits in the rest. It also made sharing a schema hard.

## Decision

The schema lives in a versioned **kit** inside the engine: `src/kb_distillery/kits/<name>/kit.toml`. A knowledge base names one kit with `[kb] kit`.

A knowledge base may extend the kit with its own `[types]` and `[edges]`. The merge rules are fixed:

- Tables merge key by key.
- Lists join, with the kit's entries first.
- A value the kit already sets must be equal. A different value is an error.

So a knowledge base can add and cannot rename, recolor or remove. To change what a kit defines, change the kit.

A kit can build on another with `extends`. This layers skills, defaults and hooks. It does not copy types. A kit lists every type it uses.

A kit also carries what goes with the schema: skills, hooks, agent instructions and default documents. `distill init` copies them into a new knowledge base. `distill init --refresh` re-syncs them and never touches knowledge.

The word "template" was the first name. The key `template` and the old names `starter` and `academic-research` are still read and map to `base` and `research`.

## Consequences

- One schema fix reaches every knowledge base that uses the kit.
- A knowledge base stays small: a `kb.toml` and its content.
- Users write kits without changing the engine code, using `KB_KITS_DIR` to try them.
- The `areas` whitelist stays with the knowledge base, because each area needs a topic page there.

## Where

`src/kb_distillery/config/kit.py`, `src/kb_distillery/kits/`, `tests/config/test_kit.py`, `tests/config/test_kit_contract.py`.
