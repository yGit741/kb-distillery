#!/usr/bin/env python3
"""Agent shell guard: block ad-hoc git/gh writes; allow only the lane entry points.

Shared by Cursor (beforeShellExecution: {"command": ...}, JSON verdict on stdout)
and Claude Code (PreToolUse Bash: {"tool_input": {"command": ...}}, exit 2 to deny).
Wired through .cursor/hooks/block-git-write.sh.

Rules:
  - A command that is exactly ONE allowlisted invocation (pixi run ship, ops, …)
    is allowed, whatever its arguments say. Chaining (; && || | > <), newlines,
    $( … ) and backticks disqualify it from the allowlist.
  - Otherwise every git/gh invocation anywhere in the command is checked by
    token: history/ref writes and destructive commands are denied, read-only
    commands (log, diff, status, show, for-each-ref, tag -l, …) pass.

This is a guardrail against agent mistakes, not a security boundary.
"""
import json
import os
import re
import shlex
import sys

ALLOW_PIXI_TASKS = {"daily-sync", "ship", "lanes", "ops", "curate-history", "install-hooks", "share"}
ALLOW_SCRIPTS = {"backend/src/kb/maintenance/daily_sync.py", "backend/src/kb/git/ship.py", "backend/src/kb/git/curate_history.py"}
ALLOW_MODULES = {"kb.ops", "kb.maintenance.daily_sync", "kb.git.ship", "kb.git.curate_history"}

BLOCKED_GIT = {
    "commit", "push", "merge", "rebase", "cherry-pick", "revert", "reset", "restore",
    "stash", "clean", "update-ref", "commit-tree", "filter-branch", "filter-repo",
    "replace", "notes", "am", "pull",
}
GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
GH_PR_READONLY = {"view", "list", "status", "diff", "checks"}
GH_REPO_BLOCKED = {"edit", "delete", "rename", "archive", "unarchive", "set-default"}
OPERATOR_CHARS = set("();<>|&")

DENY_MSG = ("Git write blocked — knowledge commits go through pixi run ops / daily-sync; "
            "tooling ships via pixi run ship (start/commit/pr/merge) when the user asks.")


def _tokens(command):
    """Shell-ish tokens; $( and backticks become separators so inner commands are scanned."""
    flat = command.replace("$(", " ; ").replace("`", " ; ")
    lex = shlex.shlex(flat, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def _is_operator(tok):
    return bool(tok) and set(tok) <= OPERATOR_CHARS


def _segments(tokens):
    seg = []
    for tok in tokens:
        if _is_operator(tok):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def _is_python(tok):
    return re.fullmatch(r"(.*/)?python(3(\.\d+)?)?", tok) is not None


def is_allowlisted(command):
    """True when the whole command is a single allowlisted lane invocation."""
    if "\n" in command or "\r" in command or "$(" in command or "`" in command:
        return False
    try:
        toks = _tokens(command)
    except ValueError:
        return False
    if not toks or any(_is_operator(t) for t in toks):
        return False
    if len(toks) >= 3 and toks[0] == "pixi" and toks[1] == "run":
        return toks[2] in ALLOW_PIXI_TASKS
    if len(toks) >= 2 and _is_python(toks[0]):
        if any(toks[1] == s or toks[1].endswith("/" + s) for s in ALLOW_SCRIPTS):
            return True
        if len(toks) >= 3 and toks[1] == "-m" and toks[2] in ALLOW_MODULES:
            return True
    return False


def _git_violation(args):
    """args = tokens after `git`. Return a reason string or None."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in GIT_GLOBAL_WITH_VALUE:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        break
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if "--no-verify" in rest:
        return "git --no-verify"
    if sub in BLOCKED_GIT:
        return f"git {sub}"
    if sub == "tag":
        writes = {"-a", "-s", "-u", "-d", "--delete", "-f", "--force", "-m", "-F", "--annotate", "--sign"}
        if any(r in writes for r in rest):
            return "git tag (write)"
        listing = not rest or "-l" in rest or "--list" in rest or all(r.startswith("-") for r in rest)
        return None if listing else "git tag <name>"
    if sub == "branch":
        if any(r in {"-d", "-D", "--delete", "-f", "--force", "-m", "-M", "--move", "-c", "-C"} for r in rest):
            return "git branch (delete/move/force)"
        return None
    if sub == "checkout":
        if any(r in {"-f", "--force", "-B", "--"} for r in rest) or "." in rest:
            return "git checkout (discard/force)"
        return None
    if sub == "config":
        if any(r.lower() == "core.hookspath" for r in rest) and "--get" not in rest:
            return "git config core.hooksPath"
        return None
    if sub == "update-index" and any(r.startswith("--assume-unchanged") or r == "--skip-worktree" for r in rest):
        return "git update-index (hide changes)"
    return None


def _gh_violation(args):
    if not args:
        return None
    sub, rest = args[0], args[1:]
    if sub == "pr":
        action = rest[0] if rest else "list"
        return None if action in GH_PR_READONLY else f"gh pr {action}"
    if sub == "repo" and rest and rest[0] in GH_REPO_BLOCKED:
        return f"gh repo {rest[0]}"
    if sub == "release" and rest and rest[0] in {"create", "delete", "edit", "upload"}:
        return f"gh release {rest[0]}"
    if sub == "api":
        method = None
        for j, r in enumerate(rest):
            if r in {"-X", "--method"} and j + 1 < len(rest):
                method = rest[j + 1].upper()
            elif r.startswith("--method="):
                method = r.split("=", 1)[1].upper()
            elif r in {"-f", "-F", "--field", "--raw-field", "--input"} and method is None:
                method = "POST"
        if method and method != "GET":
            return f"gh api {method}"
    return None


def violation(command):
    """Return a reason string when the command must be blocked, else None."""
    if is_allowlisted(command):
        return None
    try:
        toks = _tokens(command)
    except ValueError:
        # unparseable (unbalanced quotes): fail closed only if git/gh is mentioned
        return "unparseable command mentioning git/gh" if re.search(r"\b(git|gh)\b", command) else None
    for seg in _segments(toks):
        for k, tok in enumerate(seg):
            base = tok.rsplit("/", 1)[-1]
            if base == "git":
                why = _git_violation(seg[k + 1:])
            elif base == "gh":
                why = _gh_violation(seg[k + 1:])
            else:
                continue
            if why:
                return why
    return None


def _read_payload(raw):
    data = json.loads(raw or "{}")
    ti = data.get("tool_input")
    if isinstance(ti, dict):
        return "claude", ti.get("command") or ""
    return "cursor", data.get("command") or ""


def main():
    try:
        client, command = _read_payload(sys.stdin.read())
    except ValueError:
        print("git_guard: unreadable hook payload", file=sys.stderr)
        return 2
    why = violation(command)
    if why is None:
        if client == "cursor":
            print(json.dumps({"permission": "allow"}))
        return 0
    msg = f"{DENY_MSG} ({why})"
    if client == "claude":
        print(msg, file=sys.stderr)
        return 2
    print(json.dumps({
        "permission": "deny",
        "user_message": msg,
        "agent_message": "Do not run git/gh writes directly. Use pixi run ops, daily-sync or ship.",
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
