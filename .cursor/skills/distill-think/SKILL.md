---
name: distill-think
description: Two-phase distill of think-* human zones into graph brief + KB patches. Use for distill-think, distill think, graph brief.
---

# Distill think

Distill human deliberation from `think-*` pages into the public knowledge graph.

## Triggers

- `distill-think`, `distill think`, `graph brief`
- Phase 2 only on explicit `apply` or user says "apply distill"

## Rules

1. **Never edit the human zone** (`<!-- human-zone -->` … `<!-- end-human-zone -->`).
2. **Phase 1 always:** run propose, show the graph brief, stop.
3. **Phase 2 only when asked:** run apply after user reviews `plan.json`.

## Phase 1 — propose

```bash
python3 -m meta.distill propose think-<slug>
```

- Reads human zone only.
- Writes `meta/.distill/<id>/plan.json`.
- Replaces agent zone with collapsible graph brief.
- **No other wiki mutations.**

Graph brief must include:

- **Touches** — linked wiki slugs
- **Themes detected**
- **Weak / missing links**
- **Proposed edits** table (target, action, rationale)
- **Not promoting** — stays in think only

## Phase 2 — apply

```bash
python3 -m meta.distill apply think-<slug>
python3 -m meta.distill apply think-<slug> --only 2,4   # partial
python3 -m meta.distill abort think-<slug>
```

- Backs up targets, applies proposals, runs lint, rolls back on failure.
- Updates agent zone with applied status.
- Appends `meta/log.md`.

When patching public pages, cite think pages as `[[think-...]]` in thread text.

## Plan actions

| action | target |
|--------|--------|
| `append_threads` | MOC `## Threads` |
| `append_papers` | MOC `## Papers` |
| `update_section` | q-* section (e.g. Current state) |
| `append_related` | concept `related:` frontmatter |

## Agent constraints

- Direct writes to `wiki/think-*.md` are blocked by `meta/guard.py`.
- Use the CLI; do not StrReplace think files.
