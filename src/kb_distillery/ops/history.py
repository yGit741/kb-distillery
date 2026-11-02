"""Parsed first-parent history of main — shared by `ops log` and the Lifecycle tab."""
import os
import subprocess
import sys

from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
from kb_distillery.git import commit_policy as cp


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False).stdout


def tag_map(root):
    """{commit sha: snapshot tag} for kb-* tags."""
    out = _git(root, "for-each-ref", "refs/tags/kb-*", "--format=%(refname:short) %(*objectname) %(objectname)")
    tags = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            tags[parts[1]] = parts[0]
        elif len(parts) == 2:
            tags[parts[1]] = parts[0]
    return tags


def timeline(root, ref="main", limit=200):
    """Newest-first list of first-parent commits with parsed convention fields."""
    out = _git(root, "log", "--first-parent", f"-n{limit}", "--format=%H%x1f%P%x1f%aI%x1f%B%x1e", ref, "--")
    tags = tag_map(root)
    rows = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if "\x1f" not in rec:
            continue
        sha, parents, date, body = rec.split("\x1f", 3)
        c = cp.parse_message(body)
        rows.append({
            "sha": sha, "short": sha[:9], "date": date, "subject": c.subject, "kind": c.kind,
            "type": c.type, "scope": c.scope, "summary": c.summary,
            "kb_version": cp.fmt_version(c.version) if c.version else None,
            "pr": c.pr, "retro": c.retro, "parents": parents.split(),
            "op": c.trailers.get("KB-Op"), "target": c.trailers.get("KB-Target"),
            "reverts": c.trailers.get("KB-Reverts"), "reverted_by": None,
            "snapshot_tag": tags.get(sha),
        })
    by_sha = {r["sha"]: r for r in rows}
    for r in rows:
        if r["reverts"] and r["reverts"] in by_sha:
            by_sha[r["reverts"]]["reverted_by"] = r["sha"]
    return rows
