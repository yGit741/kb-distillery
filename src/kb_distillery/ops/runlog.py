"""Structured run log: one JSON line per nightly run in meta/.ops/runs.jsonl (gitignored).

The launchd log (~/Library/Logs/thesis-kb-daily-sync.log) stays the human transcript; this file is
what the Ops tab and future reports read. A record is a plain dict — `started`, `duration`,
`status` (ok | warn | error), `sync`, `deploy`, `hygiene`, `threads`, `notify`, `steps` — and
never holds secrets. The file keeps the last MAX_RUNS records. Writing never raises.
"""
import datetime
import json
import os
import re
import sys
import time

from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb_distillery.vault.schema import OPS_DIR

RUNS_FILE = "runs.jsonl"
MAX_RUNS = 120


def path(root):
    return os.path.join(root, OPS_DIR, RUNS_FILE)


class Run:
    """Collects steps of one run, then `finish()` appends the record."""

    def __init__(self, root, kind="nightly", now=None):
        self.root, self.t0 = root, time.monotonic()
        started = now or datetime.datetime.now(datetime.timezone.utc)
        self.record = {"kind": kind, "started": started.isoformat(timespec="seconds"), "steps": []}

    def step(self, name, status="ok", **fields):
        self.record["steps"].append({"name": name, "status": status,
                                     "t": round(time.monotonic() - self.t0, 2), **fields})
        return self

    def set(self, **fields):
        self.record.update(fields)
        return self

    def finish(self, status=None):
        self.record["duration"] = round(time.monotonic() - self.t0, 2)
        if status:
            self.record["status"] = status
        append(self.root, self.record)
        return self.record


def append(root, record, max_runs=MAX_RUNS):
    """Append one record and trim to the newest `max_runs`; never raises (prints a note instead)."""
    p = path(root)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        with open(p, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > max_runs + max_runs // 4:
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(lines[-max_runs:])
            os.replace(tmp, p)
    except OSError as e:
        print(f"note: run log not written — {e}")


RUN_HEADER = re.compile(r"^=== (\w{3} \w{3} +\d+ \d\d:\d\d:\d\d) (?:\S+ )?(\d{4})\s*$")
HYGIENE_LINE = re.compile(r"^hygiene: (?:clean|(\d+) error\(s\), (\d+) warning\(s\))")
NOTIFY_LINE = re.compile(r"^notify: (sent|same report already sent|no keychain item|email not sent)")


def parse_transcript(text):
    """Runs from the free-text launchd log (one `=== <date>` block each), oldest first —
    the history from before runs.jsonl existed. Records carry `"source": "log"`."""
    runs, cur = [], None
    for line in (text or "").splitlines():
        m = RUN_HEADER.match(line)
        if m:
            try:
                when = datetime.datetime.strptime(f"{m.group(1)} {m.group(2)}", "%a %b %d %H:%M:%S %Y").astimezone()
            except ValueError:
                cur = None
                continue
            cur = {"kind": "nightly", "source": "log", "started": when.isoformat(timespec="seconds"),
                   "status": "ok", "hygiene": {"errors": 0, "warnings": 0, "findings": []}, "steps": []}
            runs.append(cur)
            continue
        if cur is None:
            continue
        h = HYGIENE_LINE.match(line)
        if h and h.group(1) is not None:
            cur["hygiene"]["errors"], cur["hygiene"]["warnings"] = int(h.group(1)), int(h.group(2))
            cur["status"] = "error" if int(h.group(1)) else "warn" if int(h.group(2)) else cur["status"]
        n = NOTIFY_LINE.match(line)
        if n:
            cur["notify"] = {"sent": "sent", "same report already sent": "throttled"}.get(n.group(1), "not-sent")
        if line.startswith("Traceback") or "nightly sync FAILED" in line:
            cur["status"] = "error"
    return runs


def read(root, n=30, kind=None):
    """Newest-first list of up to `n` records (corrupt lines are skipped)."""
    try:
        with open(path(root), encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if kind and rec.get("kind") != kind:
            continue
        out.append(rec)
        if len(out) >= n:
            break
    return out
