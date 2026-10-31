---
name: propose-relations
description: >-
  Propose typed relations (extends, uses, contradicts, example-of, open-problem-in, addresses, student-of) between
  wiki pages with a batch LLM run, review them per subject, then write the ones the user accepts into the pages. Use
  for propose relations, typed edges, review or apply relation proposals. Do NOT use to answer questions from the
  wiki (query-knowledge), or to apply before the user has said which to accept.
---

# propose-relations

**LLM tier:** light · **Budget:** ~1–2k per subject (Sonnet batch, about $0.005–0.02 a subject); `apply` is zero LLM

`python -m kb.graph.propose` asks the LLM, once per subject page, which typed relations its text supports toward a small candidate list (its linked pages + top-5 vector neighbours). Proposals land only in `<kb>/.cache/relations-proposals.jsonl` (run state in `.cache/relations-propose/<run>/`); `submit`, `collect` and `review` change nothing in `wiki/`, `raw/`, `think/` or `meta/`. `apply` is the one step that edits pages, and only inside a `wiki-edit` session after the user has chosen what to accept.

## Triggers

- `propose relations`, `relation proposals`, `typed edges`, `review relation proposals`, `apply relation proposals`

## Do NOT

- Submit without a `--dry-run` first, or over the user's cap: the run spends money (batch default)
- Run `apply --write` before the user has named a confidence cutoff (or kinds / subjects): there is no default on purpose
- Run `apply --write` outside `ops begin refine …` / `ops commit`, or without a `kb-snapshot` tag first
- Run while another transactional workflow needs the same kb's attention: one LLM run at a time

## CLI

```bash
python3 -m kb.graph.propose --kb <id> submit --run <name> --dry-run          # count, estimate, worst case
python3 -m kb.graph.propose --kb <id> submit --run <name> [--backend batch|api|subscription] [--model sonnet] [--include-easy] [--include-people] [--limit N] [--max-usd 6]
python3 -m kb.graph.propose --kb <id> collect --run <name> [--wait 3600]
python3 -m kb.graph.propose --kb <id> review --run <name> [--min-confidence 0.7]
python3 -m kb.graph.propose --kb <id> status [--run <name>]
python3 -m kb.graph.propose --kb <id> repack --run <name>        # rebuild the proposals file from saved run state (no LLM): older runs kept weak rows only as rejected
python3 -m kb.graph.propose --kb <id> apply --min-confidence 0.9 [--run <name>] [--kinds uses,extends] [--subjects a,b] [--limit N]          # dry run: lists what it would write
python3 -m kb.graph.propose --kb <id> apply --min-confidence 0.9 … --write                                                                    # inside an ops session
```

## Agent steps

1. **Estimate** — `submit --dry-run`; tell the user the subject count, estimate and worst case. Backend: `--backend`, else `$KB_LLM_BACKEND`, else batch.
2. **Submit** only after the user agrees to the spend; `--max-usd` refuses a run whose estimate passes it. Re-running `submit` sends only new subjects (`--retry` resends failed/rejected).
3. **Collect** — batches end within hours; `collect` again later if one is still running. It validates every proposal (candidate slug, allowed kind, endpoint types, contradicts note, confidence within 0..1) and keeps the rest in the run's `rejected` bucket with a reason. **Confidence is data, not a gate:** weak proposals are stored too, and the cutoff is chosen when you look (`review`/`apply --min-confidence`, the Relations screen). `submit --keep-above X` sets a cutoff at creation instead (default 0, keep all).
4. **Review** — `review` prints a per-subject markdown digest (kind, target title, note, evidence, confidence); hand it to the user and ask which to accept (a cutoff, kinds, or subjects).
5. **Apply** — `ops -- snapshot "before relations"`, then `apply …` as a dry run and show the list. After the user's go (the write guard warns on wiki edits outside an open ops session): `ops begin refine relations "<why>"`, `apply … --write` (small batches with `--limit`), `ops commit`. `apply` takes a row only when lint would accept it (kind declared in `[edges]`, target exists, a note where required), skips relations a page already states (and a symmetric pair stated from the other side), and merges into an existing `relations:` block; nothing else in a page changes.

## Output

`<kb>/.cache/relations-proposals.jsonl` rows `{from, to, kind, note, confidence, evidence, origin: "llm", model, run, at}` (`tier: "low"` for `--include-easy` subjects). `apply --write` edits `relations:` blocks in `wiki/` pages, committed as `kb(refine)`.

## Quality bar

- Dry-run shown before any spend; the run stayed under `--max-usd`
- `review` digest handed over; `apply` ran only after the user chose what to accept, in a snapshot-backed ops session
- `pixi run lint` is clean after an apply (the relations lint is the same check)

## Next step

`kb-undo` for a batch the user does not want.
