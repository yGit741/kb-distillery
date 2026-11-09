"""The night window: while it is open, holds do not block agents.

The user opens it with their word ("go" to the work-all-night skill, or `pixi run ship -- night start`).
It is a small JSON marker in the git common dir (shared by every worktree) with a hard expiry, so a
forgotten window closes itself and a stale one never keeps holds off for days.

While open: `ship pr` labels nothing `hold` (schema/paradigm included), `ship merge` merges a PR that
carries a `hold` label (the merge is still pinned to the head sha it gated), and the merge-nudge Stop hook
stays silent. CI and tests are untouched: a red `all-green` still blocks the merge.
`ship approve` stays user-only; the window never lifts anything by itself outside `ship merge`.
"""
import json
import os
import time
from datetime import datetime, timedelta

from kb_distillery.git.queue import common_dir

MARKER = "kb-night.json"
DEFAULT_HOURS = 10.0
MAX_HOURS = 16.0


def _path(root):
    return os.path.join(common_dir(root), MARKER)


def _read(root):
    try:
        with open(_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def until_ts(root, now=None):
    """Epoch seconds the window closes, or None when it is closed or expired."""
    data = _read(root)
    try:
        until = float((data or {}).get("until"))
    except (TypeError, ValueError):
        return None
    return until if until > (time.time() if now is None else now) else None


def active(root, now=None):
    return until_ts(root, now) is not None


def _parse_until(text, now):
    """`HH:MM` = the next time the clock shows it (local time)."""
    hh, mm = text.split(":")
    t = datetime.fromtimestamp(now).replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    if t.timestamp() <= now:
        t += timedelta(days=1)
    return t.timestamp()


def start(root, until=None, hours=None, now=None):
    """Open the window; returns the closing epoch. Capped at MAX_HOURS."""
    now = time.time() if now is None else now
    if until:
        end = _parse_until(until, now)
    else:
        end = now + 3600 * float(hours if hours is not None else DEFAULT_HOURS)
    end = min(end, now + 3600 * MAX_HOURS)
    with open(_path(root), "w", encoding="utf-8") as f:
        json.dump({"started": now, "until": end}, f)
    return end


def stop(root):
    try:
        os.remove(_path(root))
        return True
    except OSError:
        return False


def describe(root, now=None):
    end = until_ts(root, now)
    if end is None:
        return "night window: closed (holds apply)"
    return "night window: open until " + datetime.fromtimestamp(end).strftime("%Y-%m-%d %H:%M") + " (holds do not block)"
