"""Chat sessions: one server-side home, one JSON file per session under `<kb>/.local/sessions/<id>.json`.

The browser keeps the open chat while it streams and mirrors the finished document here after every turn
(`PUT /api/sessions/{id}`), so "where are my old chats" has one answer. The files are machine-local: `.local/` is never
committed (`distill init` ignores it; the first write also adds it to the repository's local exclude file, so a kb created
before that rule never shows it as untracked).

Document: `{id, title, created, updated, model?, effort?, backend?, messages: [...], usage: {cost_usd, turns}}`.
`messages` is stored as the frontend keeps it (opaque dicts, never interpreted beyond the first user line and the usage
totals). `usage` is computed here from the messages: `turns` = questions asked, `cost_usd` = the sum of the answers'
`usage.cost_usd` (subscription turns carry no billed cost and add nothing).

Pure file logic, HTTP-free: failures are `SessionsError(status, message)` for the router to relay (400 invalid, 404 unknown,
405 read-only, 409 damaged file). Reads are tolerant: a damaged file is skipped by the list and a 409 on its own `get`.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import tempfile
import threading

from kb_distillery.config.paths import vault_root

DEFAULT_ROOT = vault_root()
READ_ONLY_ENV = "KB_READ_ONLY"
LOCAL_DIR = ".local"
SESSIONS_REL = f"{LOCAL_DIR}/sessions"
MAX_ID = 64
MAX_TITLE = 120
MAX_PREVIEW = 140
MAX_BYTES = 4 * 1024 * 1024            # the same cap as a request body
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,%d}$" % (MAX_ID - 1))
_LOCK = threading.Lock()               # routes run in a thread pool: read-modify-write must not interleave


class SessionsError(Exception):
    """A refusal with an HTTP-ish status (400 invalid, 404 unknown, 405 read-only, 409 damaged) and a plain message."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


# ---------- guards and validation ----------

def read_only_reason():
    """Why writes are refused, or None when they are allowed."""
    if os.environ.get(READ_ONLY_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
        return f"this server is read-only ({READ_ONLY_ENV} is set): chat sessions cannot be changed here"
    return None


def _check_writable():
    reason = read_only_reason()
    if reason:
        raise SessionsError(405, reason)


def clean_id(session_id):
    if not isinstance(session_id, str) or not ID_RE.match(session_id):
        raise SessionsError(400, f"a session id is letters, digits, dashes and underscores (at most {MAX_ID})")
    return session_id


def clean_title(title):
    if not isinstance(title, str) or not title.strip():
        raise SessionsError(400, "a session needs a title")
    return " ".join(title.split())[:MAX_TITLE]


def _clean_messages(messages):
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        raise SessionsError(400, "messages is a list of message objects")
    return messages


def _opt(value, name):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 200:
        raise SessionsError(400, f"{name} is a short string")
    return value


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_user_line(messages):
    for m in messages:
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            for line in m["content"].splitlines():
                if line.strip():
                    return " ".join(line.split())
    return ""


def usage_of(messages):
    turns = sum(1 for m in messages if m.get("role") == "user")
    cost = 0.0
    for m in messages:
        u = m.get("usage")
        if m.get("role") == "assistant" and isinstance(u, dict) and isinstance(u.get("cost_usd"), (int, float)) \
                and not isinstance(u.get("cost_usd"), bool):
            cost += u["cost_usd"]
    return {"cost_usd": round(cost, 6), "turns": turns}


# ---------- files ----------

def _dir(root):
    return os.path.join(root, SESSIONS_REL)


def _path(root, session_id):
    return os.path.join(_dir(root), clean_id(session_id) + ".json")


def _atomic_write(full, text):
    """Write beside the target, then rename over it: a concurrent reader sees the old file or the new, never a half."""
    os.makedirs(os.path.dirname(full), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(full), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, full)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def _exclude_file(root):
    """The repository's local exclude file for a kb checkout (None when the kb is not a repo or it cannot be found)."""
    dot = os.path.join(root, ".git")
    if os.path.isfile(dot):                                  # a linked worktree: ".git" is a pointer file
        try:
            with open(dot, encoding="utf-8") as f:
                line = f.read().strip()
        except OSError:
            return None
        if not line.startswith("gitdir:"):
            return None
        dot = os.path.normpath(os.path.join(root, line[len("gitdir:"):].strip()))
        common = os.path.join(dot, "commondir")              # the shared info/ lives in the common dir
        if os.path.isfile(common):
            with contextlib.suppress(OSError), open(common, encoding="utf-8") as f:
                dot = os.path.normpath(os.path.join(dot, f.read().strip()))
    if not os.path.isdir(dot):
        return None
    return os.path.join(dot, "info", "exclude")


def ensure_local_ignored(root):
    """Add `.local/` to the repository's local exclude file when it is missing (untracked, per clone). Best effort."""
    exclude = _exclude_file(root)
    if not exclude:
        return
    rule = f"{LOCAL_DIR}/"
    try:
        try:
            with open(exclude, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        if rule in (line.strip() for line in text.splitlines()):
            return
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as f:
            f.write(("" if not text or text.endswith("\n") else "\n") + rule + "\n")
    except OSError:
        pass


def _read(root, session_id):
    """The stored document. 404 when absent, 409 when the file is damaged."""
    full = _path(root, session_id)
    try:
        with open(full, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SessionsError(404, f"no session {session_id!r}") from None
    except (OSError, ValueError):
        raise SessionsError(409, f"session file {session_id}.json is damaged; remove it or save the chat again") from None
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        raise SessionsError(409, f"session file {session_id}.json is damaged; remove it or save the chat again")
    return _normal(session_id, data)


def _normal(session_id, data):
    """A stored document in its public shape (tolerates files written by other versions)."""
    messages = [m for m in data["messages"] if isinstance(m, dict)]
    title = data.get("title") if isinstance(data.get("title"), str) and data["title"].strip() else ""
    created = str(data.get("created") or "")
    return {
        "id": session_id,
        "title": title or _first_user_line(messages)[:MAX_TITLE] or "Untitled chat",
        "created": created,
        "updated": str(data.get("updated") or created),
        "model": data["model"] if isinstance(data.get("model"), str) else None,
        "effort": data["effort"] if isinstance(data.get("effort"), str) else None,
        "backend": data["backend"] if isinstance(data.get("backend"), str) else None,
        "messages": messages,
        "usage": usage_of(messages),
    }


def _write(root, doc):
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise SessionsError(400, f"a session is at most {MAX_BYTES // (1024 * 1024)} MB")
    ensure_local_ignored(root)
    _atomic_write(_path(root, doc["id"]), text)


# ---------- operations ----------

def summary(doc):
    return {"id": doc["id"], "title": doc["title"], "created": doc["created"], "updated": doc["updated"],
            "turns": doc["usage"]["turns"], "cost_usd": doc["usage"]["cost_usd"],
            "preview": _first_user_line(doc["messages"])[:MAX_PREVIEW],
            "model": doc["model"], "effort": doc["effort"], "backend": doc["backend"]}


def list_sessions(root=None):
    """Summaries, newest first (by `updated`, then `created`, then id). Damaged files are skipped."""
    root = root or DEFAULT_ROOT
    try:
        names = os.listdir(_dir(root))
    except OSError:
        return {"sessions": []}
    out = []
    for name in names:
        sid = name[:-5] if name.endswith(".json") else ""
        if not sid or not ID_RE.match(sid):
            continue
        try:
            out.append(summary(_read(root, sid)))
        except SessionsError:
            continue
    out.sort(key=lambda s: (s["updated"], s["created"], s["id"]), reverse=True)
    return {"sessions": out}


def get_session(session_id, root=None):
    return _read(root or DEFAULT_ROOT, clean_id(session_id))


def put_session(session_id, messages, title=None, created=None, model=None, effort=None, backend=None, root=None):
    """Upsert the whole document. A new session takes `created` from the caller (when given) or now; an existing one keeps
    its `created`, and keeps its title unless one is passed (so a rename survives the next save). `updated` is now."""
    _check_writable()
    root = root or DEFAULT_ROOT
    sid = clean_id(session_id)
    messages = _clean_messages(messages)
    fields = {"model": _opt(model, "model"), "effort": _opt(effort, "effort"), "backend": _opt(backend, "backend")}
    with _LOCK:
        try:
            old = _read(root, sid)
        except SessionsError as e:
            if e.status == 404:
                old = None
            elif e.status == 409:
                old = None              # a damaged file is replaced by the document the caller holds
            else:
                raise
        now = now_iso()
        if title is not None and str(title).strip():
            new_title = clean_title(title)
        elif old:
            new_title = old["title"]
        else:
            new_title = _first_user_line(messages)[:MAX_TITLE] or "Untitled chat"
        doc = {"id": sid, "title": new_title,
               "created": old["created"] if old and old["created"] else (_opt(created, "created") or now),
               "updated": now, **fields, "messages": messages, "usage": usage_of(messages)}
        _write(root, doc)
    return doc


def rename_session(session_id, title, root=None):
    _check_writable()
    root = root or DEFAULT_ROOT
    sid = clean_id(session_id)
    new_title = clean_title(title)
    with _LOCK:
        doc = _read(root, sid)
        doc = {**doc, "title": new_title, "updated": now_iso()}
        _write(root, doc)
    return doc


def delete_session(session_id, root=None):
    _check_writable()
    root = root or DEFAULT_ROOT
    sid = clean_id(session_id)
    with _LOCK:
        try:
            os.remove(_path(root, sid))
        except FileNotFoundError:
            raise SessionsError(404, f"no session {sid!r}") from None
    return {"ok": True, "id": sid}
