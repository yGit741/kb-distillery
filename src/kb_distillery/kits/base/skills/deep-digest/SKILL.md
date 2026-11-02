---
name: deep-digest
description: Deep digest with neighbor links (~25-40k+ tokens, HEAVY). Use ONLY when user explicitly says "deep-digest" or "deep digest" AND confirms heavy tier. Never auto-trigger.
---

# deep-digest

**LLM tier:** heavy · **Budget:** ~25–40k+ tokens in

**Requires explicit user permission** — nothing in this vault should run heavy without it.

## Triggers

- `deep-digest`, `deep digest` **and** user confirms heavy tier

## Do NOT

- Auto-trigger from `digest`, `full-digest`, or paper mentions
- Trigger on bare `digest` — ask tier first
- Run without `--confirm-heavy` on CLI
- Skip neighbor / topic / q- stub planning
- Run the paper session on a video (`raw/videos/…/video.md`): a video's deep tier is
  `distill ingest video-digest <raw> --tier deep` and then the neighbor/Connections work by hand

## CLI

```bash
distill ingest deep-digest <raw> --confirm-heavy
distill ingest deep-digest <collection-slug> --row N --confirm-heavy   # course/series row
```

Same pipeline as `full-digest` plus extended `plan.json` (neighbor papers, q- stubs, topic-page `theme-*` threads).
Books are digested one part at a time (`--part N` / `--pages A-B`) — see full-digest § Books.
Course/series rows use `--row N`; the page type follows the raw format — see full-digest § Course / series rows.

## Output

A Source page at `depth: deep` (deepened in place), `maturity: digested`, Key equations + extended
Connections required.

## Pitfalls

- The negation-word polarity check is now a warning (score capped at 60): it only fires when a negation sits within a few tokens of topic words the other page asserts, and never between a paper and its own new stubs. Do not reword honest assumptions to silence it; `coherence dismiss <id>` if it is spurious.
- A paper with long appendices (60+ pages) is treated as a paper when it has an abstract and no chapter outline; otherwise pass `--whole-book`.
- Idea and `q-` stubs are registered with the session automatically (map and finalize), so an aborted finalize removes them and restores topic-page `## Papers` lines; the old `staging/` is kept as `staging-aborted-<time>/`, and `begin` restores `claims.json`/`plan.json` of an aborted session.
- Topic slugs in `claims.json` `concepts` (a protocol key, kept) map to `area:`, not to new idea pages.
- A `q-` stub's H1 is the question's short name (≤ 80 chars, lint errors above); write the formal statement under `## Question` (required) before `finalize`.

## Summary

After finalize, refresh the page's `description:` (schema 1.3): `python3 -m kb_distillery.digest run --slugs <slug>` then `python3 -m kb_distillery.digest apply --slugs <slug>` inside the open ops session — a deeper page always gets a new one; skip pages whose `generated.by` is a `human:<id>`.

## Commit

The CLI commits this operation itself as `kb(digest): … (kb-x.y.z)` on main — only the files it changed (`--no-commit` to skip). Check with `distill ops log -n 1`. `finalize` is the commit point.
