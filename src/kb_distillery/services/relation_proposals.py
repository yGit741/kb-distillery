"""Relation proposals for the browser screen: every proposal a run made, filterable by confidence.

Source: the kb's `.cache/relations-proposals.jsonl` (written by `python -m kb_distillery.graph.propose`). It holds EVERY valid
proposal, weak ones included; confidence is data and the cutoff is chosen here, at query time. A row below
`propose.MIN_CONFIDENCE` (0.5, the default review cutoff) is labelled `low-confidence`. A proposal that failed a
structural check (an edge type the kb does not allow between those pages) was never a proposal and is not in the
file. A file written by an older run that dropped weak rows is completed with `propose repack --run <name>`.
Nothing is written. Read-only, no LLM.
"""
from __future__ import annotations

import json
import os

from kb_distillery import paths
from kb_distillery.graph import propose

PROPOSED, LOW = "proposed", "low-confidence"
BUCKETS = 10


def _cache() -> str:
    return os.path.join(paths.ROOT, ".cache")


def _accepted() -> list[dict]:
    path = os.path.join(_cache(), propose.OUT_FILE)
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("from") and r.get("to") and r.get("kind"):
                rows.append(r)
    return rows


def _titles(slugs: set[str]) -> dict[str, str]:
    from kb_distillery.search.semfind import load_pages
    pages = load_pages(paths.ROOT)
    return {s: propose._title(pages[s][2], s) if s in pages else s for s in slugs}


def load() -> list[dict]:
    """Every proposal once, per (from, to, kind), with its `status` label derived from the confidence."""
    seen, out = set(), []
    for r in _accepted():
        key = (r["from"], r["to"], r["kind"])
        if key in seen:
            continue
        seen.add(key)
        try:
            r["confidence"] = float(r["confidence"])
        except (TypeError, ValueError):
            continue
        r["status"] = LOW if r["confidence"] < propose.MIN_CONFIDENCE else PROPOSED
        out.append(r)
    return out


def query(lo: float = 0.0, hi: float = 1.0, kind: str | None = None) -> dict:
    """{rows, total, shown, kinds, histogram} for confidence in [lo, hi] (and one kind when given).

    `histogram` counts ALL proposals of the chosen kind in ten buckets of 0.1 (0.0-0.1 ... 0.9-1.0, the last one
    includes 1.0), whatever the range, so the slider can show where the mass is. Rows are best confidence first."""
    allrows = load()
    kinds = sorted({r["kind"] for r in allrows})
    scoped = [r for r in allrows if not kind or r["kind"] == kind]
    histogram = [0] * BUCKETS
    for r in scoped:
        histogram[min(int(r["confidence"] * BUCKETS), BUCKETS - 1)] += 1
    chosen = sorted((r for r in scoped if lo <= r["confidence"] <= hi),
                    key=lambda r: (-r["confidence"], r["from"], r["to"], r["kind"]))
    titles = _titles({r["from"] for r in chosen} | {r["to"] for r in chosen}) if chosen else {}
    rows = [{"from": r["from"], "from_title": titles[r["from"]], "to": r["to"], "to_title": titles[r["to"]],
             "kind": r["kind"], "confidence": r["confidence"], "note": r.get("note") or "",
             "evidence": r.get("evidence") or "", "status": r["status"], "run": r.get("run") or ""} for r in chosen]
    return {"rows": rows, "total": len(scoped), "shown": len(rows), "kinds": kinds, "histogram": histogram}
