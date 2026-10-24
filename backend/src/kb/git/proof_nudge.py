#!/usr/bin/env python3
"""Claude Code `Stop` hook: a reply that finished frontend or data work must show its proof.

When the turn (every tool call after the last human message) wrote to a frontend or data path —
`frontend/`, `backend/src/kb/dashboard/`, `wiki/`, `raw/`, `meta/` — or ran a knowledge/PR step
(`ops -- commit`, `ship -- pr|merge`, `share -- …`), the reply must carry a line

    Proof: <link> [<link> …]

with at least one clickable thing the user can open to see the result: an http(s) URL (localhost
page, PR, deployed site, artifact) or a path to a screenshot/GIF (.png/.jpg/.gif/.webp/.mp4).
Otherwise it answers `{"decision": "block", "reason": …}` once and the agent adds it.

Read-only turns, tooling-only turns and the second pass exit 0 silently. Test by hand:

    echo '{"cwd": ".", "transcript_path": "/dev/null"}' | python3 -m kb.git.proof_nudge
"""
import json
import os
import re
import sys

from kb.git.merge_nudge import last_reply

PROOF_PATHS = ("frontend/", "backend/src/kb/dashboard/", "wiki/", "raw/", "meta/")
PROOF_COMMANDS = re.compile(r"\bops\s+--\s+commit\b|\bship\s+--\s+(pr|merge)\b|\bshare\s+--\s+\w")
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}
LINK = re.compile(r"https?://\S+|\S+\.(png|jpe?g|gif|webp|mp4)\b", re.I)
PROOF_LINE = re.compile(r"^\W*proof\W*:(.*)$", re.I | re.M)


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


def needs_proof(calls):
    """Why this turn needs proof (a short phrase), or '' when it does not."""
    for name, inp in calls:
        if name in WRITE_TOOLS:
            path = str(inp.get("file_path") or inp.get("notebook_path") or "")
            hit = next((p for p in PROOF_PATHS if f"/{p}" in path or path.startswith(p)), None)
            if hit:
                return f"it edited {hit}"
        elif name == "Bash":
            cmd = str(inp.get("command") or "")
            m = PROOF_COMMANDS.search(cmd)
            if m:
                return f"it ran `{m.group(0)}`"
    return ""


def has_proof(text):
    return any(LINK.search(m.group(1)) for m in PROOF_LINE.finditer(text or ""))


def decide(payload):
    """Return the hook's JSON output (dict) or None for a silent exit."""
    if payload.get("stop_hook_active"):
        return None                                       # already asked once this stop
    why = needs_proof(turn_tool_calls(payload.get("transcript_path")))
    if not why:
        return None
    text = payload.get("last_assistant_message") or last_reply(payload.get("transcript_path"))
    if has_proof(text):
        return None
    return {"decision": "block",
            "reason": f"This turn changed something the user will want to see ({why}). Before you finish, "
                      "add a line `Proof: <link> …` with links that show the result clearly: the "
                      "localhost page or deployed URL of the screen you changed, a screenshot/GIF path "
                      "you captured, the PR URL, or the wiki page / commit (kb-x.y.z) you wrote. If it can't "
                      "be shown yet, take a screenshot first (Playwright) rather than skipping it."}


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
