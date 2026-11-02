---
name: kb-snapshot
description: >-
  Freeze the knowledge base as an annotated tag kb-x.y.z, list snapshots, or bring wiki/ back to one
  as a new kb(restore) commit. Use for snapshot, freeze, tag version, restore snapshot, go back to kb-x.y.z.
  Do NOT use to undo a single step (use kb-undo) or to share (sharing is built from a snapshot later).
---

# kb-snapshot

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `snapshot`, `freeze the kb`, `tag this state`, `snapshot "week 43"`
- `restore kb-x.y.z`, `go back to last week's snapshot` — only when the user asks

## Do NOT

- Create tags with `git tag` — blocked; snapshots are made by `distill ops snapshot` (annotated, named after the version)
- Restore without the user naming or confirming the snapshot
- Expect restore to touch `raw/` or `think/` — it never does

## CLI

```bash
distill ops snapshot "week 43"
distill ops snapshots
distill ops restore kb-0.7.4
```

## Agent steps

1. Snapshot: `distill ops snapshot "<label>"` → tags the newest knowledge step `kb-x.y.z` (if main's tip is an infra merge, the last knowledge step is tagged).
2. Restore: `distill ops snapshots`, confirm the tag with the user, then `distill ops restore <tag>`. Requires no uncommitted `wiki/` edits.
3. Tags are pushed by the nightly sync (`--follow-tags`).

## Output

- Snapshot: annotated tag `kb-x.y.z` with the label as its message.
- Restore: one new commit `kb(restore): back to kb-x.y.z (kb-…)` with `KB-Snapshot`; `wiki/`, `meta/aliases.tsv`, `meta/chats/` match the tag; `wiki/log.md` gets a `restore` entry.

## Next step

`kb-history` to confirm the new state.
