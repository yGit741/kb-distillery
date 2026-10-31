"""Relation proposals for the browser screen: every proposal a run made, accepted or not, filterable by confidence.

Two sources in the kb's `.cache/` (written by `python -m kb.graph.propose`): `relations-proposals.jsonl` holds the
accepted ones (confidence >= 0.5, valid endpoints), and each run's `relations-propose/<run>/state.json` keeps the
rejected ones. A proposal rejected only for low confidence is shown too, marked `low-confidence`; one rejected for a
structural reason (an edge type the kb does not allow between those pages) is not a proposal and is left out.
Nothing is written. Read-only, no LLM.
"""
from __future__ import annotations

import glob
import json
import os

from kb import paths
from kb.graph import propose

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
                rows.append({**r, "status": PROPOSED})
    return rows


def _low_confidence() -> list[dict]:
    rows = []
    for state in sorted(glob.glob(os.path.join(_cache(), "relations-propose", "*", "state.json"))):
        try:
            with open(state, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        for t in (data.get("subjects") or {}).values():
            for r in t.get("rejected") or []:
                if str(r.get("reason", "")).startswith("confidence") and "missing" not in str(r.get("reason")):
                    rows.append({**r, "status": LOW, "run": data.get("run")})
    return rows


def _titles(slugs: set[str]) -> dict[str, str]:
    from kb.search.semfind import load_pages
    pages = load_pages(paths.ROOT)
    return {s: propose._title(pages[s][2], s) if s in pages else s for s in slugs}


def load() -> list[dict]:
    """Every proposal once, per (from, to, kind): an accepted one wins over a low-confidence one."""
    seen, out = set(), []
    for r in _accepted() + _low_confidence():
        key = (r["from"], r["to"], r["kind"])
        if key in seen:
            continue
        seen.add(key)
        try:
            r["confidence"] = float(r["confidence"])
        except (TypeError, ValueError):
            continue
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
