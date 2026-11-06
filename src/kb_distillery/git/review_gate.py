"""Reviewer pass record: `ship pr` opens a PR only for a head commit the reviewer subagent has passed.

The reviewer is a Claude subagent (`.claude/agents/reviewer.md`), not a script, so the lead records the
verdict: `ship review --pass "<one-line summary>" [--findings N]` stores the branch's HEAD sha in
`kb-reviews.json` in the git common dir (shared by every worktree, never tracked). A new commit changes
HEAD, so the record goes stale and `ship pr` asks for a fresh review. `ship pr --no-review "<reason>"`
bypasses the check; the reason lands in the PR body.
"""
import fcntl
import json
import os
import tempfile

from kb_distillery.git.queue import common_dir

FILE = "kb-reviews.json"


def _path(root):
    return os.path.join(common_dir(root), FILE)


def _read(root):
    try:
        with open(_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record(root, branch, sha, summary, findings=None):
    path = _path(root)
    with open(path + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)         # released when the file closes
        data = _read(root)
        data[branch] = {"sha": sha, "summary": summary.strip(), "findings": findings}
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=FILE + ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


def passed(root, branch, sha):
    """The record for `branch` when it was made at exactly `sha`, else None."""
    rec = _read(root).get(branch)
    return rec if isinstance(rec, dict) and rec.get("sha") == sha and sha else None


def summary_line(rec):
    n = rec.get("findings")
    return rec.get("summary", "") + (f" ({n} findings)" if n is not None else "")
