"""Build the Ops tab snapshot — the same data as the nightly report mail, live (0 LLM).

Read-only apart from running the hygiene checks (git reads, `gh pr list`, the Cloudflare snapshot
listing). Always describes the primary checkout, so a dashboard started from a worktree still
shows the whole vault. Results are cached for CACHE_SECONDS; `refresh=True` reruns them.
"""
import datetime
import os
import sys
import threading
import time

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

ROOT = vault_root()
CACHE_SECONDS = 60
LOG_LINES = 120
_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()


def vault_root():
    try:
        from kb.git import ship
        return ship.primary_checkout(ROOT)
    except Exception:  # noqa: BLE001 — fall back to this checkout
        return ROOT


def _run_summary(rec):
    hy = rec.get("hygiene") or {}
    return {"started": rec.get("started"), "status": rec.get("status") or "info", "duration": rec.get("duration"),
            "source": rec.get("source", "runlog"),
            "notify": rec.get("notify"), "sync": rec.get("sync") or {}, "deploy": rec.get("deploy") or {},
            "errors": hy.get("errors", 0), "warnings": hy.get("warnings", 0),
            "findings": hy.get("findings", []), "threads": len(rec.get("threads") or []),
            "steps": rec.get("steps", [])}


def run_history(root, n=30):
    """Newest-first runs: meta/.ops/runs.jsonl, topped up from the launchd transcript for older nights."""
    from kb.ops import runlog
    from kb.ops.core import NIGHTLY_LOG
    runs = runlog.read(root, n)
    if len(runs) < n:
        try:
            with open(NIGHTLY_LOG, encoding="utf-8", errors="replace") as f:
                older = runlog.parse_transcript(f.read())
        except OSError:
            older = []
        oldest = runs[-1]["started"] if runs else None
        cutoff = datetime.datetime.fromisoformat(oldest) if oldest else None
        older = [r for r in older if not cutoff or datetime.datetime.fromisoformat(r["started"]) < cutoff
                 - datetime.timedelta(minutes=10)]
        runs += list(reversed(older))[: n - len(runs)]
    return runs


def log_tail(n=LOG_LINES):
    from kb.ops.core import NIGHTLY_LOG
    from kb.report import sanitize
    try:
        with open(NIGHTLY_LOG, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return ""
    root = vault_root()
    return "\n".join(sanitize.short_path(sanitize.strip_ansi(line.rstrip("\n")), root) for line in lines)


def _build():
    from kb.ops import core, nightly_report
    root = vault_root()
    now = datetime.datetime.now(datetime.timezone.utc)
    report, threads, doc = nightly_report.collect(root, now)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "root": os.path.basename(root),
        "subject": nightly_report.subject(doc, report),
        "doc": doc.as_dict(),
        "threads": [t.as_dict() for t in threads],
        "hygiene": report.as_dict(),
        "runs": [_run_summary(r) for r in run_history(root)],
        "nightly": core.nightly_status(root),
        "log": log_tail(),
    }


def merge_queue():
    """Live merge-queue state (cheap file read, never cached); None when it cannot be read."""
    from kb.git import queue
    try:
        return queue.state(vault_root())
    except Exception:  # noqa: BLE001 — the tile shows "unknown" rather than failing the snapshot
        return None


def build_ops_snapshot(refresh=False):
    with _lock:
        if refresh or not _cache["data"] or time.monotonic() - _cache["at"] > CACHE_SECONDS:
            _cache["data"], _cache["at"] = _build(), time.monotonic()
        data = _cache["data"]
    return {**data, "queue": merge_queue()}


def email_preview():
    """The exact HTML (and subject) the nightly mail would carry right now."""
    from kb.report import model, render_html
    data = build_ops_snapshot()
    return render_html.render(model.Doc.from_dict(data["doc"])), data["subject"]
