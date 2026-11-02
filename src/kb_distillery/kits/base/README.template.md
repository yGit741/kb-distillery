# {{name}}

A knowledge base made with kb-distillery from the `{{kit}}` kit. It is its own git repository: raw inputs go in `raw/inbox/`, an agent digests them into a linked `wiki/`, and every change is one `kb(<op>)` commit.

Run these from this folder:

```bash
distill doctor                 # check the environment and this kb
distill launch    # open the explorer
distill lint      # the linter is the schema
```

- `AGENTS.md` is the rule file every agent working here reads first.
- `.claude/skills/`, `.claude/docs/`, `.claude/hooks/` and `.claude/settings.json` are copies from the kit. Update them with `distill init --refresh`; they never touch `raw/`, `wiki/`, `meta/` or this folder's `AGENTS.md`.
- `kb.toml` says what this knowledge base is (kit, schema version, its own page types).
