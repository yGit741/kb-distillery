---
name: lint-moc
description: On-demand theme MOC semantic lint. Fix internal issues; external paper tensions → Connections bullets.
---

# lint-moc

**LLM tier:** medium · **Budget:** ~8–20k tokens · **One MOC at a time**

## Triggers

- `lint-moc`, `lint moc`, `check theme moc-info-theory`

## Phase 1 — bundle (0 LLM)

```bash
python3 meta/semfind.py moc moc-info-theory
python3 meta/semfind.py moc moc-tensor-factorization --max-pairs 10
```

## Phase 2 — review

1. Read `meta/.semfind/moc-<slug>/bundle.md` + `coherence.json`.
2. Separate **internal** (fix) from **external** (Connections notes on papers).
3. Write `findings.md` in session dir; summarize in chat.
4. Promote fixes via normal ingest/distill — never auto-write wiki.

## Paper disagreement

Not a failure. For each `external` pair, draft Connections bullets for both papers; user/agent adds them manually; `python3 meta/coherence.py noted <id>`.
