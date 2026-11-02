#!/usr/bin/env python3
"""Claude Code `Stop` hook: a reply that finished user-visible work must show its proof.

The turn (every tool call after the last human message) is classified into kinds; each kind asks
for its own evidence on the reply's `Proof:` line(s). Every requirement is an any-of group, and all
groups of every kind the turn touched must be met:

    ui         web/                               local URL  +  deployed URL (always both)
    api        kb_distillery/server/, kb_distillery/services/        local endpoint URL
    knowledge  wiki/, raw/, meta/, ops commit   page link  +  kb-x.y.z or commit URL
    pr         ship pr / merge              PR URL
    deploy     share -- …                   deployed URL

Missing evidence answers `{"decision": "block", "reason": …}` once, naming what is missing.
Read-only turns, other tooling and the second pass exit 0 silently. Test by hand:

    echo '{"cwd": ".", "transcript_path": "/dev/null"}' | python3 -m kb_distillery.git.proof_nudge
"""
import json
import os
import re
import sys

from kb_distillery.git.merge_nudge import last_reply

DEPLOYED_SITE = "https://kb.yonatan-magen-thesis.workers.dev"
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}
PROOF_LINE = re.compile(r"^\W*proof\W*:(.*)$", re.I | re.M)

# evidence: name -> (description, regex)
LOCAL = ("a local URL (http://localhost:5173/… of the changed screen)", r"https?://(localhost|127\.0\.0\.1)(:\d+)?\S*")
DEPLOYED = (f"the deployed URL ({DEPLOYED_SITE}/…)", r"https://\S+\.(workers|pages)\.dev\S*")
PAGE = ("a link to the wiki page (deployed or local)", r"https?://(localhost|127\.0\.0\.1|\S+\.(workers|pages)\.dev)\S*")
VERSION = ("the kb-x.y.z version or commit URL", r"\bkb-\d+\.\d+\.\d+\b|github\.com/\S+/commit/[0-9a-f]{7,}")
PR = ("the PR URL (github.com/…/pull/N)", r"github\.com/\S+/pull/\d+")

# kind -> (path prefixes, command regex, [any-of evidence groups])
KINDS = {
    "ui": (("web/",), None, [[LOCAL], [DEPLOYED]]),
    "api": (("src/kb_distillery/server/", "src/kb_distillery/services/"), None, [[LOCAL]]),
    "knowledge": (("wiki/", "raw/", "meta/"), r"\bops\s+--\s+commit\b", [[PAGE], [VERSION]]),
    "pr": ((), r"\bship\s+--\s+(pr|merge)\b", [[PR]]),
    "deploy": ((), r"\bshare\s+--\s+\w", [[DEPLOYED]]),
}


def turn_tool_calls(transcript_path):
    """(name, input) of every tool call after the last human message."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return []
    calls = []
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                content = (o.get("message") or {}).get("content")
                blocks = content if isinstance(content, list) else []
                if o.get("type") == "user":
                    if not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks):
                        calls = []                        # a human message: the turn starts after it
                elif o.get("type") == "assistant":
                    calls += [(b.get("name", ""), b.get("input") or {}) for b in blocks
                              if isinstance(b, dict) and b.get("type") == "tool_use"]
    except OSError:
        return []
    return calls


def _under(path, prefix):
    return f"/{prefix}" in path or path.startswith(prefix)


def turn_kinds(calls):
    """Kinds of work this turn did, in KINDS order."""
    hit = set()
    for name, inp in calls:
        path = str(inp.get("file_path") or inp.get("notebook_path") or "") if name in WRITE_TOOLS else ""
        cmd = str(inp.get("command") or "") if name == "Bash" else ""
        for kind, (prefixes, cmd_re, _) in KINDS.items():
            if (path and any(_under(path, p) for p in prefixes)) or (cmd and cmd_re and re.search(cmd_re, cmd)):
                hit.add(kind)
    return [k for k in KINDS if k in hit]


def missing_proof(kinds, text):
    """{kind: [missing requirement descriptions]} given the reply's Proof: lines."""
    proof = "\n".join(m.group(1) for m in PROOF_LINE.finditer(text or ""))
    out = {}
    for kind in kinds:
        miss = [" or ".join(d for d, _ in group) for group in KINDS[kind][2]
                if not any(re.search(rx, proof, re.I) for _, rx in group)]
        if miss:
            out[kind] = miss
    return out


def decide(payload):
    """Return the hook's JSON output (dict) or None for a silent exit."""
    if payload.get("stop_hook_active"):
        return None                                       # already asked once this stop
    kinds = turn_kinds(turn_tool_calls(payload.get("transcript_path")))
    if not kinds:
        return None
    text = payload.get("last_assistant_message") or last_reply(payload.get("transcript_path"))
    miss = missing_proof(kinds, text)
    if not miss:
        return None
    lines = "\n".join(f"- {k}: " + "; ".join(m) for k, m in miss.items())
    return {"decision": "block",
            "reason": "This turn changed something the user will want to see. Before you finish, add "
                      f"`Proof:` line(s) with links covering:\n{lines}\n"
                      "Start the app and deploy if needed (`pixi run share -- …`); a UI change always shows "
                      "both its local and its deployed URL — a screenshot does not replace either."}


def main():
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except ValueError:
        payload = {}
    out = decide(payload if isinstance(payload, dict) else {})
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
