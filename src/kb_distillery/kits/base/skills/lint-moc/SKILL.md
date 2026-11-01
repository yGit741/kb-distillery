---
name: lint-moc
description: On-demand semantic audit of one topic page (theme-*). Use for lint-moc, lint moc, lint topic. Do NOT auto-edit wiki for external disagreements.
---

# lint-moc

**LLM tier:** medium · **Budget:** ~8–20k tokens · **One topic page at a time**

A topic audit: topic pages (`type: topic`, `layer: concept`, slug `theme-<slug>`, one per
TOPIC_SLUGS entry). The skill keeps its historical name `lint-moc`.

## Triggers

- `lint-moc`, `lint moc`, `lint topic`, `lint theme`, `check topic theme-info-theory`

## Do NOT

- Auto-edit wiki for `external` paper disagreements — suggest Connections bullets only
- Run on entire vault — one topic at a time

## Phase 1 — bundle (0 LLM)

```bash
python3 -m kb_distillery.search.semfind topic theme-info-theory
python3 -m kb_distillery.search.semfind topic theme-tensor-factorization --max-pairs 10
```

`theme` and `moc` are kept as CLI aliases of `topic`.

## Phase 2 — review

1. Read `meta/.semfind/moc-theme-<slug>/bundle.md` + `coherence.json`.
2. Separate **internal** (fix) from **external** (Connections notes on Source pages).
3. Write `findings.md` in session dir; summarize in chat.
4. Promote fixes via normal ingest/distill — never auto-write wiki.

## Paper disagreement

Not a failure. For each `external` pair, draft Connections bullets for both pages; user/agent adds them manually; `python3 -m kb_distillery.core.coherence noted <id>`.

## Commit

The topic audit itself is read-only. Wrap any wiki fix in an ops session so it becomes one undoable commit: `distill ops begin refine <slug> "why"` → edit → `distill ops commit` (see `wiki-edit`).
