---
name: lint-moc
description: On-demand semantic lint of one theme page (theme-*, formerly MOC). Use for lint-moc, lint moc. Do NOT auto-edit wiki for external disagreements.
---

# lint-moc

**LLM tier:** medium · **Budget:** ~8–20k tokens · **One theme page at a time**

Theme pages (`theme-<slug>`, one per THEME_SLUGS entry) replaced the old `moc-*` pages; the
skill keeps its name.

## Triggers

- `lint-moc`, `lint moc`, `lint theme`, `check theme theme-info-theory`

## Do NOT

- Auto-edit wiki for `external` paper disagreements — suggest Connections bullets only
- Run on entire vault — one theme at a time

## Phase 1 — bundle (0 LLM)

```bash
python3 meta/semfind.py theme theme-info-theory
python3 meta/semfind.py theme theme-tensor-factorization --max-pairs 10
```

`moc` is still accepted as an alias of `theme`.

## Phase 2 — review

1. Read `meta/.semfind/moc-theme-<slug>/bundle.md` + `coherence.json`.
2. Separate **internal** (fix) from **external** (Connections notes on reading units).
3. Write `findings.md` in session dir; summarize in chat.
4. Promote fixes via normal ingest/distill — never auto-write wiki.

## Paper disagreement

Not a failure. For each `external` pair, draft Connections bullets for both pages; user/agent adds them manually; `python3 meta/coherence.py noted <id>`.

## Commit

The theme pass itself is read-only. Wrap any wiki fix in an ops session so it becomes one undoable commit: `pixi run ops -- begin refine <slug> "why"` → edit → `pixi run ops -- commit` (see `wiki-edit`).
