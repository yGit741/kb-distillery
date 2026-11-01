---
name: kb-undo
description: >-
  Reverse one knowledge step (e.g. an idea split that should not have happened) as a new kb(undo)
  commit that rewrites only wiki/. Use for undo, revert step, roll back <slug>. Do NOT use for infra
  changes, think/ edits, raw/ imports, or to go back to a whole earlier state (use kb-snapshot restore).
---

# kb-undo

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `undo <step|sha|slug>`, `revert that split`, `roll back the last digest`
- Only when the user asks — never undo on your own initiative

## Do NOT

- Use `git revert` / `git reset` — blocked; `ops undo` is the only path
- Undo `kb(think)` (the user's own notes) or `kb(import)` (raw inbox files) — refused by design
- Undo an infra commit — that is a new PR
- Chain undos without confirming each with the user

## CLI

```bash
distill ops log --kb
distill ops undo 3f9c2ba
distill ops status
```

## Agent steps

1. `distill ops log --kb` and identify the step with the user (version `kb-x.y.z` + subject).
2. Confirm which step to undo.
3. `distill ops undo <sha>`. It refuses when later steps changed the same files and lists them — undo those first, newest first, after confirming.
4. Report the new `kb(undo)` version.

## Output

New commit `kb(undo): revert <version> <summary> (kb-x.y.z)` with `KB-Reverts: <sha>`. Only `wiki/`, `meta/aliases.tsv`, `meta/chats/` are rewritten; lint regenerates `index.md` / `corpus.tsv` (an un-digested paper is simply re-queued); `meta/log.md` gets an `undo` entry. History is never rewritten.

## Next step

`kb-history` to confirm; `semantic-lint-hop` if links around the undone pages need a look.
