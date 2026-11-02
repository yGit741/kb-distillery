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

from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

ROOT = vault_root()
CACHE_SECONDS = 60
LOG_LINES = 120
_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()


def vault_root():
    try:
        from kb_distillery.git import ship
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
    from kb_distillery.ops import runlog
    from kb_distillery.ops.core import NIGHTLY_LOG
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
    from kb_distillery.ops.core import NIGHTLY_LOG
    from kb_distillery.ops.report import sanitize
    try:
        with open(NIGHTLY_LOG, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return ""
    root = vault_root()
    return "\n".join(sanitize.short_path(sanitize.strip_ansi(line.rstrip("\n")), root) for line in lines)


def _build():
    from kb_distillery.ops import core, nightly_report
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
    from kb_distillery.git import queue
    try:
        return queue.state(vault_root())
    except Exception:  # noqa: BLE001 — the tile shows "unknown" rather than failing the snapshot
        return None


OWNER_PLIST = os.path.expanduser("~/Library/LaunchAgents/com.kb-distillery.deploy-owner.plist")
OWNER_HEARTBEAT = 900   # the owner cycles every 300 s; three missed cycles = not running
OUTCOMES = ("deployed", "rolled-back", "failed", "rollback-failed")
IN_FLIGHT = ("building", "uploading", "deploying")
PENDING = IN_FLIGHT + ("failed-network", "failed-module")


def _ts(iso):
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (t if t.tzinfo else t.astimezone()).timestamp()
    except (TypeError, ValueError):
        return None


def _read_json(path):
    import json
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _origin_main(root):
    """(sha, unix commit time) of origin/main as last fetched; (None, None) when unreadable."""
    import subprocess
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%H %ct", "origin/main"], cwd=root,
                             capture_output=True, text=True, timeout=10).stdout.split()
        return (out[0], int(out[1])) if len(out) == 2 else (None, None)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, None


def deploy_state(root=None, now=None, plist=OWNER_PLIST, main=None):
    """The deploy owner's state (kb_distillery.publish.cloudflare.owner: .cache/share/owner.json + status.json) vs origin/main.

    Read-only. A field is None when unknown so the tile says "unknown" rather than ok. `main` = (sha, unix
    time) overrides the git read (tests).
    """
    root = root or vault_root()
    now = time.time() if now is None else now
    cache = os.path.join(root, ".cache", "share")
    owner = _read_json(os.path.join(cache, "owner.json"))
    status = _read_json(os.path.join(cache, "status.json"))
    shas = owner.get("shas") or {}
    rows = sorted(((s, e) for s, e in shas.items() if isinstance(e, dict)),
                  key=lambda r: r[1].get("at", ""), reverse=True)
    live, live_at = next(((s, _ts(e.get("at"))) for s, e in rows if e.get("state") == "deployed"), (None, None))
    if status.get("state") in ("deployed", "skipped-same") and status.get("sha"):  # also covers direct deploys
        st_at = _ts(status.get("at"))
        if live is None or (st_at and (not live_at or st_at > live_at)):
            live, live_at = status["sha"], st_at
    last = next(((s, e) for s, e in rows if e.get("state") in OUTCOMES), None)
    deploying = next((s for s, e in rows if e.get("state") in IN_FLIGHT), None)
    if not deploying and status.get("state") == "deploying":
        deploying = status.get("sha")
    main_sha, main_time = main if main is not None else _origin_main(root)
    behind = None if not (live and main_sha) else live != main_sha
    cutoff = now - 7 * 86400
    # heartbeat: the cycle start, or any later step a long cycle (build, retry backoff) recorded
    beat = max([t for t in [_ts(owner.get("last_cycle_at"))] + [_ts(e.get("at")) for _, e in rows[:1]] if t] or [0]) or None
    return {
        "live_sha": live,
        "live_at": datetime.datetime.fromtimestamp(live_at, datetime.timezone.utc).isoformat(timespec="seconds")
        if live_at else None,
        "main_sha": main_sha,
        "behind": behind,
        "behind_minutes": (max(0, int((now - main_time) // 60)) if main_time else None) if behind else
        (0 if behind is False else None),
        "deploying": deploying,
        "last_outcome": last[1].get("state") if last else None,
        "last_sha": last[0] if last else None,
        "last_reason": (last[1].get("error") or last[1].get("note") or "") if last else "",
        # pending entries recorded before the live deploy are superseded, not queued (older owners never marked them)
        "queued": [s for s, e in rows if e.get("state") in PENDING and s != live
                   and not (live_at and (_ts(e.get("at")) or 0) < live_at)],
        "rollbacks_7d": sum(1 for _, e in rows if e.get("state") == "rolled-back" and (_ts(e.get("at")) or 0) >= cutoff),
        "owner_installed": os.path.isfile(plist),
        "owner_alive": bool(beat and now - beat <= OWNER_HEARTBEAT),
        "heartbeat_age": int(now - beat) if beat else None,
    }


def deploy():
    """Live deploy-owner state (cheap file reads, never cached); None when it cannot be read."""
    try:
        return deploy_state()
    except Exception:  # noqa: BLE001 — the tile shows "unknown" rather than failing the snapshot
        return None


def build_ops_snapshot(refresh=False):
    with _lock:
        if refresh or not _cache["data"] or time.monotonic() - _cache["at"] > CACHE_SECONDS:
            _cache["data"], _cache["at"] = _build(), time.monotonic()
        data = _cache["data"]
    return {**data, "queue": merge_queue(), "deploy": deploy()}


def email_preview():
    """The exact HTML (and subject) the nightly mail would carry right now."""
    from kb_distillery.ops.report import model, render_html
    data = build_ops_snapshot()
    return render_html.render(model.Doc.from_dict(data["doc"])), data["subject"]
