#!/usr/bin/env python3
"""Claude Code `Stop` hook: never let a reply end while a PR silently waits for "merge".

Reads the hook JSON on stdin. When the session's cwd is on an `infra/<feature>` branch that has
an OPEN pull request and the reply just written does not carry the nudge line, it answers
`{"decision": "block", "reason": …}` once, so the agent appends:

    Awaiting your merge: #N <title> <url> — say "merge" to merge it, or "drop" to discard it.

A PR is always named "#N title", never a bare number: a nudge without the PR's title does not count.

Everything else (main, no PR, gh/network unavailable, nudge already present, second pass) exits
0 silently. Test by hand:

    echo '{"cwd": ".", "transcript_path": "/dev/null"}' | python3 -m kb.git.merge_nudge
"""
import json
import os
import subprocess
import sys

NUDGE_MARK = "awaiting your merge"
GH_TIMEOUT = 8


def _git(cwd, *args):
    try:
        cp = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (cp.stdout or "").strip() if cp.returncode == 0 else ""


def open_pr(cwd, branch):
    """{number, title, url} of the OPEN PR for `branch`, or None (also when gh/network is unavailable)."""
    try:
        cp = subprocess.run([os.environ.get("GH_BIN", "gh"), "pr", "view", branch, "--json", "number,title,url,state"],
                            cwd=cwd, capture_output=True, text=True, check=False, timeout=GH_TIMEOUT)
        info = json.loads(cp.stdout) if cp.returncode == 0 and cp.stdout.strip() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if not info or info.get("state") != "OPEN":
        return None
    return {"number": info.get("number"), "title": info.get("title", ""), "url": info.get("url", "")}


def last_reply(transcript_path):
    """Text of the assistant's latest reply: every assistant text block after the last human message."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return ""
    chunks = []
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                content = (o.get("message") or {}).get("content")
                blocks = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
                if o.get("type") == "user":
                    if not any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks):
                        chunks = []                       # a human message: the reply starts after it
                elif o.get("type") == "assistant":
                    chunks += [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
    except OSError:
        return ""
    return "\n".join(chunks)


def nudge_line(pr):
    title = f' {pr["title"]}' if pr.get("title") else ""
    return f'Awaiting your merge: #{pr["number"]}{title} {pr["url"]} — say "merge" to merge it, or "drop" to discard it.'


def decide(payload):
    """Return the hook's JSON output (dict) or None for a silent exit."""
    if payload.get("stop_hook_active"):
        return None                                       # already nudged once this stop
    cwd = payload.get("cwd") or os.getcwd()
    branch = _git(cwd, "symbolic-ref", "--short", "-q", "HEAD")
    if not branch.startswith("infra/"):
        return None
    pr = open_pr(cwd, branch)
    if not pr:
        return None
    text = payload.get("last_assistant_message") or last_reply(payload.get("transcript_path"))
    low = text.lower()
    if NUDGE_MARK in low and (pr.get("title") or "").lower() in low:
        return None
    return {"decision": "block",
            "reason": f"PR #{pr['number']} on {branch} is open and waits for the user's word. "
                      f"Finish your reply with exactly this line (nothing after it):\n{nudge_line(pr)}"}


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
