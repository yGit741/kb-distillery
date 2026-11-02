"""Local metrics store: JSONL files under meta/.ops/metrics/ (gitignored), pushed nightly to D1.

    sessions.jsonl     one record per Claude Code session (kb_distillery.metrics.sessions), rewritten by `ingest`
    golden.jsonl       one record per golden task run (kb_distillery.metrics.golden), append-only
    baselines/<name>.json   a frozen summary to compare later runs against

The local files are the write-ahead buffer: writing never needs the network, and D1 is a copy.
"""
import json
import os
import statistics

from kb_distillery.vault.schema import OPS_DIR
from kb_distillery.paths import vault_root

METRICS_DIR = "metrics"


def path(name, root=None):
    """Under the primary checkout even when called from a worktree: meta/.ops is gitignored, so a
    worktree's copy would vanish with it."""
    if root is None:
        from kb_distillery.git.ship import primary_checkout
        try:
            root = primary_checkout(vault_root())
        except Exception:  # noqa: BLE001 — not a git checkout (tests, exports)
            root = vault_root()
    return os.path.join(root, OPS_DIR, METRICS_DIR, name)


def read(name, root=None):
    try:
        with open(path(name, root), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return []


def write(name, records, root=None):
    p = path(name, root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    os.replace(tmp, p)


def append(name, record, root=None):
    p = path(name, root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def merge_sessions(new, root=None):
    """Upsert by id; a session whose log Claude Code already deleted keeps its last record."""
    by_id = {r["id"]: r for r in read("sessions.jsonl", root)}
    by_id.update({r["id"]: r for r in new})
    out = sorted(by_id.values(), key=lambda r: r.get("start") or "")
    write("sessions.jsonl", out, root)
    return out


def _tokens(r):
    return sum(r["main"].values()) + sum(r["sub"].values())


def summarize_sessions(records):
    """Per-task medians and totals — the shape a baseline freezes and `compare` diffs."""
    out = {}
    for task in sorted({r["task"] for r in records}):
        rs = [r for r in records if r["task"] == task]
        out[task] = {
            "n": len(rs),
            "first_context_med": statistics.median(r["first_context"] for r in rs),
            "usd_med": round(statistics.median(r["usd"] for r in rs), 3),
            "usd_sum": round(sum(r["usd"] for r in rs), 2),
            "tokens_med": statistics.median(_tokens(r) for r in rs),
            "calls_med": statistics.median(r["calls"] for r in rs),
            "sub_share": round(sum(sum(r["sub"].values()) for r in rs) / max(1, sum(_tokens(r) for r in rs)), 3),
        }
    return out


def summarize_golden(runs):
    """Per golden task: medians over the runs of one label (usd, judge score, pass rate)."""
    out = {}
    for tid in sorted({r["task"] for r in runs}):
        rs = [r for r in runs if r["task"] == tid]
        scores = [r["judge"]["score"] for r in rs if r.get("judge", {}).get("score") is not None]
        out[tid] = {
            "n": len(rs),
            "usd_med": round(statistics.median(r["usd"] for r in rs), 3),
            "first_context_med": statistics.median(r.get("first_context") or 0 for r in rs),
            "minutes_med": round(statistics.median(r["minutes"] for r in rs), 1),
            "score_med": statistics.median(scores) if scores else None,
            "pass_rate": round(sum(1 for r in rs if r.get("passed")) / len(rs), 2),
            "flagged": sum(1 for r in rs if r.get("judge", {}).get("flagged")),
        }
    return out
