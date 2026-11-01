#!/usr/bin/env python3
"""PreToolUse hook: refuse writes that would violate the vault schema.

Used by Claude Code (.claude/settings.json).
Reads the tool call JSON on stdin. Exit 2 blocks the call; stderr carries the
message for Claude; Cursor also receives JSON stdout when hook_event_name is set.
Prompt-level rules in AGENTS.md are a summary of what this file enforces.
"""
import json
import os
import sys
import time

from kb_distillery.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
VAULT_ROOT = vault_root()

from kb_distillery.core.schema import (DIGEST_DIR, DISTILL_DIR, DISTILLED_THINK_PREFIX, GENERATED, INGEST_DIR, INGEST_STALE_HOURS,
                    META_DIR as SCHEMA_META_DIR, OPS_DIR, OPS_STRICT, PARSED_FILENAME, QUARANTINE_DIR,
                    CODE_TOP_DIRS, RAW_DIR, ROOT_DIRS, ROOT_FILES, ROOT_MD, SIDECAR_ELIGIBLE_KINDS,
                    THINK_DIR, WIKI_DIR)

WRITE_TOOLS = frozenset({
  # Claude Code
  "Write", "Edit", "NotebookEdit",
  # Cursor Agent
  "StrReplace", "EditNotebook", "Delete",
})

_cursor_payload = None


SKILLS_MD_PREFIX = ".claude/skills/"      # the engine's dev skills (and a kb's copy of its kit skills) are markdown


def _open_ingest_sessions(root):
    ingest = os.path.join(root, INGEST_DIR)
    sessions = []
    if not os.path.isdir(ingest):
        return sessions
    for sha in os.listdir(ingest):
        sp = os.path.join(ingest, sha, "session.json")
        if not os.path.isfile(sp):
            continue
        try:
            with open(sp, encoding="utf-8") as f:
                s = json.load(f)
            if s.get("status") == "open":
                sessions.append(s)
        except (json.JSONDecodeError, OSError):
            continue
    return sessions


def _open_distill_sessions(root):
    distill = os.path.join(root, DISTILL_DIR)
    sessions = []
    if not os.path.isdir(distill):
        return sessions
    for sid in os.listdir(distill):
        sp = os.path.join(distill, sid, "session.json")
        if not os.path.isfile(sp):
            continue
        try:
            with open(sp, encoding="utf-8") as f:
                s = json.load(f)
            if s.get("status") == "open":
                sessions.append(s)
        except (json.JSONDecodeError, OSError):
            continue
    return sessions


def _distill_guard(rel, root):
    """Block direct wiki writes for paths owned by an open distill apply session."""
    if not rel.startswith(f"{WIKI_DIR}/"):
        return
    for s in _open_distill_sessions(root):
        if s.get("mode") != "apply":
            continue
        guarded = set(s.get("modified_files", []))
        if rel in guarded:
            deny(f"BLOCKED: {rel} is locked by distill apply session for "
                 f"`{s.get('think_path')}`. Use "
                 f"`python3 -m kb_distillery.distill apply {s.get('think_path')}` "
                 f"or `abort` — do not write wiki/ directly during an open apply session.")


def _distilled_guard(rel):
    """Agents edit distilled-think pages only via kb_distillery.distill CLI."""
    if rel.startswith(f"{WIKI_DIR}/{DISTILLED_THINK_PREFIX}") and rel.endswith(".md"):
        deny(f"BLOCKED: {rel} — use `python3 -m kb_distillery.distill propose/revise/apply` "
             "— never edit distilled-think pages via agent tools.")


def _think_guard(rel):
    """Agents must never edit think/ — human sandbox."""
    if rel == THINK_DIR or rel.startswith(f"{THINK_DIR}/"):
        deny(f"BLOCKED: {rel} is human-owned slow space under {THINK_DIR}/. "
             "Use `python3 -m kb_distillery.distill` — never edit think/ via agent tools.")


def _shared_think_guard(abs_path):
    """The shared think space (`kbs/think/`, kb_distillery.paths.THINK_PATH) sits beside every vault, so it is
    judged by absolute path before the vault-relative rules."""
    from kb_distillery.paths import THINK_PATH
    think = os.path.realpath(THINK_PATH)
    target = os.path.realpath(abs_path)
    if target == think or target.startswith(think + os.sep):
        deny(f"BLOCKED: {abs_path} is in the shared think space ({THINK_PATH}), human-owned. "
             "Use `python3 -m kb_distillery.distill` — never edit think via agent tools.")


def _ingest_guard(rel, root):
    """Block direct wiki writes for paths owned by an open ingest session."""
    if not rel.startswith(f"{WIKI_DIR}/"):
        return
    for s in _open_ingest_sessions(root):
        guarded = set(s.get("new_files", []) + s.get("modified_files", []))
        if rel in guarded:
            deny(f"BLOCKED: {rel} is locked by ingest session {s.get('sha1')} "
                 f"for `{s.get('raw')}`. Use `python3 -m kb_distillery.ingest finalize {s.get('sha1')}` "
                 f"or `abort` — do not write wiki/ directly during an open session.")


def _current_branch(root):
    """Branch of the checkout at root, read from .git without running git."""
    git = os.path.join(root, ".git")
    try:
        if os.path.isfile(git):
            with open(git, encoding="utf-8") as f:
                git = f.read().split("gitdir:", 1)[1].strip()
        with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
            head = f.read().strip()
    except (OSError, IndexError):
        return ""
    return head[len("ref: refs/heads/"):] if head.startswith("ref: refs/heads/") else ""


def _strict_or_warn(msg):
    strict = os.environ.get("KB_OPS_STRICT", "1" if OPS_STRICT else "0") == "1"
    if strict:
        deny(f"BLOCKED: {msg}")
    sys.stderr.write(f"ops warning: {msg}\n")


def _ops_guard(rel, root):
    """Free-form wiki edits belong to an open ops session → one undoable kb(...) commit."""
    branch = _current_branch(root)
    if branch.startswith("infra/"):
        _strict_or_warn(f"{rel} is knowledge — edit wiki/ on main through an ops session, not on {branch} "
                        "(schema PRs change notes through a migration).")
        return
    current = os.path.join(root, OPS_DIR, "current.json")
    if os.path.isfile(current) and time.time() - os.path.getmtime(current) < INGEST_STALE_HOURS * 3600:
        return
    _strict_or_warn(f"{rel}: no open operation. Run `pixi run ops -- begin refine <slug> \"why\"` first and "
                    "`pixi run ops -- commit` after, so this edit becomes one undoable kb(refine) commit.")


def deny(msg):
    sys.stderr.write(msg + "\n")
    if _cursor_payload is not None:
        sys.stdout.write(json.dumps({
            "permission": "deny",
            "agent_message": msg,
        }) + "\n")
    sys.exit(2)


def _is_write_tool(tool_name):
    return tool_name in WRITE_TOOLS


def _extract_path(payload):
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None
    # Claude Code: file_path; Cursor Agent: path or file_path
    for key in ("file_path", "path"):
        val = tool_input.get(key)
        if val:
            return val
    return None


def _repo_top(start):
    """The root a shell standing in `start` belongs to: the nearest folder at or above it that is a knowledge base
    (has a `kb.toml`) or a checkout (has a `.git`, a folder or the file a linked worktree has). A shell in a subfolder
    (`web/`) must not make that subfolder the root, or every path under it is judged as if it sat at the top
    (`src/api/x.ts`: "unexpected location"). A knowledge base nested in the repo (`examples/demo`) stays its own root,
    so its `raw/` and `wiki/` rules keep applying. Falls back to `start` when neither marker is found."""
    probe = os.path.realpath(start)
    while True:
        if os.path.exists(os.path.join(probe, ".git")) or os.path.isfile(os.path.join(probe, "kb.toml")):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return start
        probe = parent


def _resolve_root(payload):
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots:
        return roots[0]
    cwd = payload.get("cwd")
    if cwd:
        return _repo_top(cwd)
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")     # a deliberate root (possibly a kb nested in the repo): as given
    if env_root:
        return env_root
    return VAULT_ROOT


def _rel_path(abs_path, root):
    try:
        rel = os.path.relpath(os.path.realpath(abs_path), os.path.realpath(root))
    except ValueError:
        return None
    if rel.startswith(".."):
        return None
    return rel.replace(os.sep, "/")


WORKTREES_DIR = ".claude/worktrees"


def _in_worktree(rel, root):
    """A path inside a linked worktree (`.claude/worktrees/<name>/x`) is judged as `x` in that worktree."""
    parts = rel.split("/")
    if len(parts) > 3 and "/".join(parts[:2]) == WORKTREES_DIR:
        return "/".join(parts[3:]), os.path.join(root, *parts[:3])
    return rel, root


def _root_location_guard(rel):
    """Only schema dirs, allowlisted root files, and dot-tooling may live at vault root."""
    parts = rel.split("/")
    top = parts[0]
    if top.startswith("."):
        return
    if top in ROOT_DIRS:
        return
    if len(parts) == 1 and rel in ROOT_FILES:
        return
    if len(parts) == 1:
        deny(f"BLOCKED: {rel} — vault root files are limited to "
             f"{', '.join(sorted(ROOT_FILES))}. Move content to wiki/, raw/inbox/, or think/.")
    deny(f"BLOCKED: {rel} — unexpected location. Top-level dirs allowed: "
         f"{', '.join(sorted(ROOT_DIRS))} (+ dot-tooling like .claude/). "
         "Use raw/inbox/ for new inputs.")


def check_path(rel, root):
    """Enforce vault write policy for a repo-relative path. Calls deny() on violation."""
    parts = rel.split("/")
    top = parts[0]

    if (top == RAW_DIR and len(parts) == 4 and parts[1] in SIDECAR_ELIGIBLE_KINDS
            and parts[3] == PARSED_FILENAME):
        return  # agent-generated sidecar — see schema.py PARSED_FILENAME

    if top == RAW_DIR:
        deny(f"BLOCKED: {rel} is inside raw/, which is immutable. "
             "Raw files are user-owned inputs. Write the digest to wiki/ instead "
             "and point at the source with a `raw:` frontmatter field.")

    if top == QUARANTINE_DIR:
        deny(f"BLOCKED: {rel} is in _quarantine/, a staging area for deletion. "
             "Nothing should be authored there.")

    if rel in GENERATED:
        deny(f"BLOCKED: {rel} is generated. Do not hand-edit it. "
             "Rebuild with `python3 -m kb_distillery.lint.lint`.")

    if os.path.basename(rel) == "_index.md":
        deny("BLOCKED: no _index.md files. index.md is the single catalog, "
             "and it is generated by src/kb_distillery/lint/lint.py.")

    _root_location_guard(rel)

    if top == THINK_DIR or rel.startswith(f"{THINK_DIR}/"):
        _think_guard(rel)

    if rel.endswith(".md"):
        allowed = top in (WIKI_DIR, SCHEMA_META_DIR, DIGEST_DIR) or top in CODE_TOP_DIRS or rel in ROOT_MD or rel.startswith(SKILLS_MD_PREFIX)
        if not allowed:
            deny(f"BLOCKED: {rel} — markdown lives in wiki/, meta/, digest/ or the code folders (src/ scripts/ share/ web/ docs/ examples/). "
                 f"Allowed at root: {', '.join(sorted(ROOT_MD))}.")
        if top == WIKI_DIR and len(parts) > 2 and "excalidraw" not in parts:
            deny(f"BLOCKED: {rel} — wiki/ is flat. Use a filename prefix "
                 "(paper-, course-, theme-, q-, …) instead of a subfolder.")
        if top == WIKI_DIR:
            _distilled_guard(rel)
            _distill_guard(rel, root)
            _ingest_guard(rel, root)
            _ops_guard(rel, root)


def main():
    global _cursor_payload
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # unparseable input is not our business

    if payload.get("hook_event_name"):
        _cursor_payload = payload

    tool_name = payload.get("tool_name") or payload.get("tool") or ""
    if tool_name and not _is_write_tool(tool_name):
        sys.exit(0)

    path = _extract_path(payload)
    if not path:
        if tool_name and _is_write_tool(tool_name):
            deny(f"BLOCKED: could not parse file path from {tool_name} tool call.")
        sys.exit(0)

    root = _resolve_root(payload)
    _shared_think_guard(path)
    rel = _rel_path(path, root)
    if not rel:
        sys.exit(0)  # outside the vault
    rel, root = _in_worktree(rel, root)

    check_path(rel, root)
    if _cursor_payload is not None:
        sys.stdout.write(json.dumps({"permission": "allow"}) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
