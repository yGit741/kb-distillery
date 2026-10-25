"""Structured PR event comments: one machine-readable line per lifecycle step.

Format (one line, `·`-separated):

    kb-event v1 · <event> · <sha7> · <k=v …> · <YYYY-MM-DDTHH:MMZ>

Posting is best-effort (one retry, never raises); reading keeps only lines that start with
``kb-event v1`` so human comments cost nothing.
"""
import datetime as _dt
import os
import subprocess

PREFIX = "kb-event v1"
SEP = " · "
EVENTS = ("claimed", "queued", "checks-passed", "checks-failed", "merged", "deployed", "rolled-back")


def _now():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _clean(v):
    return str(v).replace("·", "-").replace("\n", " ").replace(" ", "_") or "-"


def format_event(event, sha="", ts=None, **kv):
    if event not in EVENTS:
        raise ValueError(f"unknown event {event!r} (one of {', '.join(EVENTS)})")
    pairs = " ".join(f"{k}={_clean(v)}" for k, v in kv.items() if v is not None) or "-"
    return SEP.join([PREFIX, event, (sha or "-")[:7], pairs, ts or _now()])


def parse_line(line):
    """dict(event, sha, kv, ts) for a kb-event line, else None."""
    line = line.strip()
    if not line.startswith(PREFIX + SEP):
        return None
    parts = line.split(SEP)
    if len(parts) != 5:
        return None
    _, event, sha, pairs, ts = parts
    kv = {}
    if pairs != "-":
        for tok in pairs.split(" "):
            k, _, v = tok.partition("=")
            if k:
                kv[k] = v
    return {"event": event, "sha": "" if sha == "-" else sha, "kv": kv, "ts": ts}


def _gh(args, root):
    exe = os.environ.get("GH_BIN", "gh")
    try:
        return subprocess.run([exe, *args], cwd=root, capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess([exe, *args], 1, "", str(e))


def post(pr, event, sha="", root=None, **kv):
    """Comment the event on PR `pr`. Returns True on success; never raises."""
    if not pr:
        return False
    try:
        body = format_event(event, sha, **kv)
    except ValueError as e:
        print(f"note: event not posted — {e}")
        return False
    for _ in range(2):
        cp = _gh(["pr", "comment", str(pr), "--body", body], root)
        if cp.returncode == 0:
            return True
    print(f"note: could not post {event} event on #{pr} — {(cp.stderr or cp.stdout).strip()[:200]}")
    return False


def read(pr, root=None):
    """Parsed kb-event lines on PR `pr`, oldest first ([] on error)."""
    cp = _gh(["api", f"repos/{{owner}}/{{repo}}/issues/{pr}/comments", "--paginate", "--jq", ".[].body"], root)
    if cp.returncode != 0:
        return []
    return [e for e in map(parse_line, cp.stdout.splitlines()) if e]


def compact(e):
    kv = " ".join(f"{k}={v}" for k, v in e["kv"].items())
    return f"{e['ts']}  {e['event']:<13} {e['sha'] or '-':<7} {kv}".rstrip()


def cmd_events(pr, root=None):
    evs = read(pr, root)
    if not evs:
        print(f"#{pr}: no kb-events")
        return 0
    for e in evs:
        print(compact(e))
    return 0
