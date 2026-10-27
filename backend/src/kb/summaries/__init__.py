"""Propose and apply `summary:` lines for wiki pages (Sonnet via `claude -p`, on the subscription).

    pixi run summarize -- plan                 # which pages need one (missing or stale)
    pixi run summarize -- run --batch 50 [--sample]   # propose → .cache/summaries/proposals.jsonl
    pixi run summarize -- show [--last 20]     # proposals next to each page's lead lines
    pixi run summarize -- judge [--slugs a,b]  # a stronger model (Fable 5.1) grades the proposals
    pixi run summarize -- apply [--slugs a,b]  # write them into wiki/ (inside an ops session)

`run` never touches wiki/: proposals land in the cache, so a bad batch costs nothing to throw away.
`apply` refuses until the schema knows the field (SCHEMA_VERSION >= 1.3) and never overwrites a summary
marked `summary_by: me`.
"""
