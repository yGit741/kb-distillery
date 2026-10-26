"""Think notes API: list / read / save the human's own notes under think/, plus quick capture.

think/ is the human's slow space (AGENTS.md): schema-free, never linted, never written by agents.
This service only acts on an explicit user action in the app (editing in the Think screen, quick
capture), so the writes are the human's own edits. It never commits — dirty think/ files are swept
into their own `kb(think)` commit by kb.ops.core before each op and nightly, exactly like edits
made in Obsidian.

Everything takes an explicit `root` so tests can run against a temp vault.
Raises ThinkError(status, message) for the HTTP layer to relay.
"""
import datetime
import os
import re

from kb.paths import vault_root

DEFAULT_ROOT = vault_root()
CAPTURE_NOTE = "inbox.md"
MAX_NOTE_BYTES = 2 * 1024 * 1024  # a note, not an attachment
_NAME = re.compile(r"[^\\/\0\r\n]{1,180}\.md")  # one path segment, .md — subfolders stay Obsidian-only


class ThinkError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _think_dir(root):
    return os.path.join(root, "think")


def _note_path(root, name):
    """think/<name> for a safe, single-segment markdown file name."""
    if not _NAME.fullmatch(name) or name.startswith(".") or ".." in name:
        raise ThinkError(400, f"not a think note name: {name!r} (a single '<name>.md' segment)")
    return os.path.join(_think_dir(root), name)


def list_notes(root=None):
    """Top-level think/*.md, newest edit first. Subfolders hold experiments, not notes."""
    root = root or DEFAULT_ROOT
    d = _think_dir(root)
    notes = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        p = os.path.join(d, name)
        if not name.endswith(".md") or name.startswith(".") or not os.path.isfile(p):
            continue
        st = os.stat(p)
        notes.append(dict(name=name, size=st.st_size, mtime=st.st_mtime))
    notes.sort(key=lambda n: -n["mtime"])
    return dict(notes=notes, capture_note=CAPTURE_NOTE)


def get_note(name, root=None):
    root = root or DEFAULT_ROOT
    path = _note_path(root, name)
    if not os.path.isfile(path):
        raise ThinkError(404, f"no think note {name!r}")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return dict(name=name, text=text, mtime=os.stat(path).st_mtime)


def _write_atomic(path, text):
    """tmp + os.replace so a crash or full disk never truncates a human-owned note."""
    tmp = path + ".kb-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def save_note(name, text, base_mtime=None, root=None, create=False):
    """Write the whole note. `base_mtime` (from get_note) refuses to clobber an edit made on disk
    meanwhile (in either direction — a restore moves mtime back); `create` refuses an existing file."""
    root = root or DEFAULT_ROOT
    if len(text.encode("utf-8")) > MAX_NOTE_BYTES:
        raise ThinkError(413, "note too large (2 MB cap)")
    path = _note_path(root, name)
    exists = os.path.isfile(path)
    if exists and create:
        raise ThinkError(409, f"{name} already exists")
    if exists and base_mtime is not None and abs(os.stat(path).st_mtime - base_mtime) > 1e-3:
        raise ThinkError(409, f"{name} changed on disk since it was loaded — reload it first")
    os.makedirs(_think_dir(root), exist_ok=True)
    _write_atomic(path, text)
    return dict(name=name, mtime=os.stat(path).st_mtime, created=not exists)


def capture(text, root=None, now=None):
    """Append a quick thought to think/inbox.md under today's heading; creates the note on first use."""
    root = root or DEFAULT_ROOT
    text = (text or "").strip()
    if not text:
        raise ThinkError(400, "nothing to capture")
    if len(text) > 10_000:
        raise ThinkError(413, "a capture is a quick thought (10k chars cap)")
    now = now or datetime.datetime.now()
    day, hhmm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    path = _note_path(root, CAPTURE_NOTE)
    old = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    lines = text.splitlines()
    entry = f"- {hhmm} — {lines[0]}" + "".join(f"\n  {ln}" for ln in lines[1:]) + "\n"
    heading = f"## {day}"
    if heading in old.splitlines():
        # append at the end of today's section (before the next heading, or EOF)
        out, placed, in_day = [], False, False
        for ln in old.splitlines(keepends=True):
            if not placed and in_day and ln.startswith("## "):
                out.append(entry)
                placed = True
            if ln.rstrip("\n") == heading:
                in_day = True
            out.append(ln)
        if not placed:
            if out and not out[-1].endswith("\n"):
                out.append("\n")
            out.append(entry)
        new = "".join(out)
    else:
        base = old if not old or old.endswith("\n") else old + "\n"
        new = (base + "\n" if base else "# Inbox\n\nQuick thoughts captured from the app.\n\n") + f"{heading}\n\n{entry}"
    os.makedirs(_think_dir(root), exist_ok=True)
    _write_atomic(path, new)
    return dict(name=CAPTURE_NOTE, mtime=os.stat(path).st_mtime, created=not old)
