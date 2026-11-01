---
name: semantic-lint-hop
description: 1-hop semantic review after ingest/distill. Fix internal ingestion issues; for external paper disagreements suggest Connections bullets only.
---

# semantic-lint-hop

**LLM tier:** light–medium · **Budget:** ~3–12k tokens

Runs after `full-digest` / `deep-digest` finalize or `distill apply` when `SEMFIND_READY` is printed.

## Triggers

- Automatically after full/deep digest finalize or distill apply (unless user says skip)
- Never after `easy-digest`

## Do NOT

- Auto-edit wiki pages
- Re-queue raw or delete digests for `external` (paper disagreement)
- Treat paper-vs-paper tension as a lint error

## Workflow

1. Read `meta/.semfind/<id>/bundle.md` and `coherence.json` only.
2. For each pair:
   - **`internal`** — digest wrong, q-* out of sync, stale vs raw → **fix** wiki or re-digest
   - **`external`** — two digested papers disagree → suggest `## Connections` / `## Links out` bullet for **each** paper:
     `- Disagrees with [[other-paper]]: …`
   - **`scope`** — different setting → note scope; dismiss
3. Write `findings.md` in the same `.semfind/` session dir.
4. High-severity internal: one line in `meta/log.md`.
5. Mark manifest: `python3 -m kb_distillery.core.coherence fixed <id>` or `noted <id>`.

## Core rule

| kind | Action |
|------|--------|
| internal | Fix ingestion — inconsistent wiki is debt |
| external | Note on paper pages only — both digests stay |

## Commit

Wrap any wiki fix in an ops session so it becomes one undoable commit: `distill ops begin refine <slug> "why"` → edit → `distill ops commit` (see `wiki-edit`).
