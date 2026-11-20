"""Staleness: diff the cards of two IR builds (two commits). A wiki page that cites a fact that was removed or changed
needs review; a fact whose only change is a line number is not stale.

    distill code stale <old_out> <new_out>      # -> <new_out>/staleness.json (always exits 0: read `fact_ids_gone`)

Build the old side without touching the checkout: KB_CODE_REPO_OVERRIDE="repo=/path/to/old/checkout" KB_CODE_OUT=<old_out>.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


def norm(t: str) -> str:
    t = re.sub(r"`([^`]*?):\d+`", r"`\1`", t)  # drop line numbers from anchors: a moved line is not a changed fact
    return re.sub(r"\s+", " ", t).strip()


def load(d: Path) -> dict[str, dict]:
    return {c["slug"]: c for c in json.loads((d / "cards" / "index.json").read_text())}


def main(old: Path, new: Path) -> dict:
    a, b = load(old), load(new)
    ma, mb = (json.loads((d / "ir.json").read_text())["meta"] for d in (old, new))
    rows = []
    for slug in sorted(set(a) | set(b)):
        fa = Counter((f["section"], norm(f["text"])) for f in a.get(slug, {}).get("fact_list", []))
        fb = Counter((f["section"], norm(f["text"])) for f in b.get(slug, {}).get("fact_list", []))
        raw_a = Counter((f["section"], f["text"]) for f in a.get(slug, {}).get("fact_list", []))
        raw_b = Counter((f["section"], f["text"]) for f in b.get(slug, {}).get("fact_list", []))
        removed, added = fa - fb, fb - fa
        same = sum((fa & fb).values())
        moved = same - sum((raw_a & raw_b).values())
        ids_a = {f["id"] for f in a.get(slug, {}).get("fact_list", [])}
        ids_b = {f["id"] for f in b.get(slug, {}).get("fact_list", [])}
        rows.append({"card": slug, "facts_old": sum(fa.values()), "facts_new": sum(fb.values()), "unchanged": same - moved, "moved_only": moved,
                     "removed": sum(removed.values()), "added": sum(added.values()),
                     "sections_changed": dict(Counter(s for s, _ in list(removed.elements()) + list(added.elements()))),
                     "fact_ids_gone": sorted(ids_a - ids_b),
                     "examples_added": [t[:260] for _, t in list(added.elements())[:4]],
                     "examples_removed": [t[:260] for _, t in list(removed.elements())[:4]]})
    changed_repos = {r for r in set(ma["repos"]) | set(mb["repos"]) if ma["repos"].get(r, {}).get("sha") != mb["repos"].get(r, {}).get("sha")}
    out = {"old": {r: ma["repos"].get(r, {}).get("sha") for r in sorted(changed_repos)},
           "new": {r: mb["repos"].get(r, {}).get("sha") for r in sorted(changed_repos)},
           "cards": rows, "cards_changed": sum(bool(r["added"] or r["removed"]) for r in rows), "cards_total": len(rows),
           "facts_added": sum(r["added"] for r in rows), "facts_removed": sum(r["removed"] for r in rows),
           "facts_moved_only": sum(r["moved_only"] for r in rows), "facts_unchanged": sum(r["unchanged"] for r in rows)}
    (new / "staleness.json").write_text(json.dumps(out, indent=1))
    for r in rows:
        if r["added"] or r["removed"]:
            print(f'{r["card"]:44s} old {r["facts_old"]:4d} new {r["facts_new"]:4d} moved {r["moved_only"]:4d} -{r["removed"]:3d} +{r["added"]:3d}')
    print({k: v for k, v in out.items() if k != "cards"})
    print(f"-> {new}/staleness.json (fact_ids_gone lists the ids a wiki page may still cite)")
    return out
