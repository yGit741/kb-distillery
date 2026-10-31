---
name: propose-relations
description: >-
  Propose typed relations (extends, uses, contradicts, example-of, open-problem-in, addresses, student-of) between
  wiki pages with a batch LLM run, then review the proposals per subject. Use for propose relations, typed edges,
  relation proposals, review relation proposals. Do NOT use to write relations into wiki pages (proposals only,
  under .cache/), or to answer questions from the wiki (query-knowledge).
---

# propose-relations

**LLM tier:** light · **Budget:** ~1–2k per subject (Sonnet batch, about $0.005–0.02 a subject)

`python -m kb.graph.propose` asks the LLM, once per subject page, which typed relations its text supports toward a small candidate list (its linked pages + top-5 vector neighbours). Proposals land only in `<kb>/.cache/relations-proposals.jsonl` (run state in `.cache/relations-propose/<run>/`); nothing in `wiki/`, `raw/`, `think/` or `meta/` changes.

## Triggers

- `propose relations`, `relation proposals`, `typed edges`, `review relation proposals`

## Do NOT

- Submit without a `--dry-run` first, or over the user's cap: the run spends money (batch default)
- Write proposals into pages: accepting one is a `wiki-edit` step the user asks for
- Run while another transactional workflow needs the same kb's attention: it is read-only on the wiki, but one LLM run at a time

## CLI

```bash
python3 -m kb.graph.propose --kb <id> submit --run <name> --dry-run          # count, estimate, worst case
python3 -m kb.graph.propose --kb <id> submit --run <name> [--backend batch|api|subscription] [--model sonnet] [--include-easy] [--include-people] [--limit N] [--max-usd 6]
python3 -m kb.graph.propose --kb <id> collect --run <name> [--wait 3600]
python3 -m kb.graph.propose --kb <id> review --run <name> [--min-confidence 0.7]
python3 -m kb.graph.propose --kb <id> status [--run <name>]
```

## Agent steps

1. **Estimate** — `submit --dry-run`; tell the user the subject count, estimate and worst case. Backend: `--backend`, else `$KB_LLM_BACKEND`, else batch.
2. **Submit** only after the user agrees to the spend; `--max-usd` refuses a run whose estimate passes it. Re-running `submit` sends only new subjects (`--retry` resends failed/rejected).
3. **Collect** — batches end within hours; `collect` again later if one is still running. It validates every proposal (candidate slug, allowed kind, endpoint types, contradicts note, confidence ≥ 0.5) and keeps the rest in the run's `rejected` bucket with a reason.
4. **Review** — `review` prints a per-subject markdown digest (kind, target title, note, evidence, confidence); hand it to the user. Accepting a proposal into a page is a separate `wiki-edit`.

## Output

`<kb>/.cache/relations-proposals.jsonl` rows `{from, to, kind, note, confidence, evidence, origin: "llm", model, run, at}` (`tier: "low"` for `--include-easy` subjects); no knowledge commit.

## Quality bar

- Dry-run shown before any spend; the run stayed under `--max-usd`
- `review` digest handed over; no file outside `.cache/` changed

## Next step

`wiki-edit` for the proposals the user accepts.
