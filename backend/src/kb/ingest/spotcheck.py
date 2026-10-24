"""Easy-digest quality spot checks (schema 1.0, S8).

Easy digests run on the cheapest model (Haiku). About 5% of them are re-read by a stronger model
(Sonnet) that compares the page's Problem / Main result with the source and logs a verdict. The
pick is deterministic (a hash of the slug), so a batch and its re-run choose the same pages, and the
log is append-only: meta/.ingest/easy/spotcheck.jsonl (local, gitignored with meta/.ingest).

    python -m kb.ingest easy-spotcheck pick <slug> [<slug> ...]      # which pages to re-read
    python -m kb.ingest easy-spotcheck log <slug> --model sonnet --verdict ok|fix [--note "…"]
    python -m kb.ingest easy-spotcheck status                       # counts per verdict
"""
import hashlib
import json
import math
import os
from datetime import datetime, timezone

from .paths import ROOT

RATE = 0.05
DEFAULT_MODEL = "haiku"          # easy-digest default
CHECK_MODEL = "sonnet"           # the stronger re-reader
VERDICTS = ("ok", "fix")
LOG = os.path.join(ROOT, "meta", ".ingest", "easy", "spotcheck.jsonl")


def _key(slug):
    return hashlib.sha1(slug.encode("utf-8")).hexdigest()


def pick(slugs, rate=RATE):
    """ceil(rate · n) of the slugs (at least one when there are any), chosen by hash — stable."""
    slugs = sorted(set(s for s in slugs if s))
    if not slugs:
        return []
    k = max(1, math.ceil(rate * len(slugs)))
    return sorted(sorted(slugs, key=_key)[:k])


def log(slug, verdict, model=CHECK_MODEL, note="", path=None):
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    path = path or LOG
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "slug": slug,
           "model": model, "verdict": verdict, "note": note}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def status(path=None):
    path = path or LOG
    counts = {v: 0 for v in VERDICTS}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    v = json.loads(line).get("verdict")
                except ValueError:
                    continue
                counts[v] = counts.get(v, 0) + 1
    return counts
