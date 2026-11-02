# Kit

A kit is the schema a knowledge base follows. It lists the page types, their filename prefixes, their colors, the extra frontmatter fields for source pages, and the typed relations a page may state.

A kit is versioned and lives in the engine: `src/kb_distillery/kits/<name>/kit.toml`. It ships inside the wheel. A knowledge base names one kit in `kb.toml` and may extend it. It cannot edit it. See [ADR 0002](../adr/0002-kits-over-templates.md).

## Kits that ship

| Kit | Builds on | For |
|---|---|---|
| `base` | none | A small general knowledge base. Source types `article`, `notes`, `document`. Concept types `topic`, `idea`, `question`, `person`. Collection type `series`. Relations `extends`, `uses`. |
| `research` | `base` | Academic reading. Adds `paper`, `lecture`, `video`, `blog-post`, `mail`, `ai-chat`, `part`, and the collections `book`, `notebook`, `course`. Adds the relations `contradicts`, `example-of`, `open-problem-in`, `addresses`, `discusses`, `student-of`. |

`examples/demo` uses `base` and adds its own types (`company`, `role`, `interview`, `skill`, `posting`). Read its `kb.toml` as a worked example of extension.

## What a kb may do

| In `kb.toml` | Rule |
|---|---|
| A table (`[types.source.paper]`) | Merged key by key with the kit's. |
| A list (`areas`, `order`, edge `types`) | Joined with the kit's. The kit's entries come first. |
| A value the kit already sets | Must be equal. The engine refuses a different value. |

A kb can add a type, an area or a relation. It cannot rename, recolor or remove what the kit defines.

## What else a kit carries

- `defaults/`: flags, the routed agent docs, page skeletons and digest instructions. A knowledge base's own `meta/` overrides them.
- `skills/`: workflow skills copied into `.claude/skills/` of each knowledge base.
- `hooks/`: the git hooks and Claude Code guards (`base` only).
- `AGENTS.template.md`: the agent instructions written into a new knowledge base.

`distill init --refresh` re-syncs an existing knowledge base with its kit. It never touches `raw/`, `wiki/`, `meta/`, `kb.toml`, `README.md` or `AGENTS.md`.

## Next

- [Write a kit](../guides/write-a-kit.md)
- Rules in full: [kits.md](../../src/kb_distillery/kits/base/defaults/docs/kits.md)
