#!/usr/bin/env python3
"""Full-text index over a kb's pages, think notes, chats and extracted raw text (SQLite FTS5, 0 LLM, 0 network).

    distill search text "<query>" [--kinds page,think] [--limit 20] [--rebuild] [--json]

The index is `<kb>/.cache/search/fts.sqlite`: machine-local, rebuilt from the files at any time, never committed
(`.cache/` is in every kb's .gitignore). `docs` holds one row per document (kind, id, title, path, mtime), `fts` the text
(title, body; `unicode61` with `remove_diacritics 2`). It is fresh by construction: `search` first runs `ensure`, which
compares a cheap stat scan with the stored (document count, newest mtime) and re-indexes only what changed; writers call
`update_quiet` (best effort, only once an index exists) so the first search after a write has nothing left to do.

Kinds and ids: `page` = wiki slug · `think` = note name · `chat` = session id (`.local/sessions/<id>.json`) · `raw` =
repo path of a text file under raw/ (`.md`, `.txt`, `parsed.md` sidecars).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import layout
from kb_distillery.storage import StorageError, for_kb
from kb_distillery.vault import frontmatter

RAW_PREFIX = "raw/"
KINDS = ("page", "think", "chat", "raw")
SCHEMA = "1"
INDEX_REL = os.path.join(".cache", "search", "fts.sqlite")
SESSIONS_REL = os.path.join(".local", "sessions")
RAW_EXTS = (".md", ".txt")
MAX_BODY = 300_000                  # bytes read of one document: a book-sized raw file is indexed by its first part
_FM = re.compile(r"\A---\n.*?\n---\n", re.S)


def index_path(root):
    return os.path.join(root, INDEX_REL)


# ---------- the sources: what exists (stat only) ----------
def _mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def _scan(root):
    """{path: (kind, id, mtime)} for every indexable file. Paths are root-relative, except the shared think space (absolute)."""
    out = {}

    def add(kind, ident, path):
        m = _mtime(_full(root, path))
        if m is not None:
            out[path] = (kind, ident, m)

    wiki = os.path.join(root, layout.WIKI_DIR)
    for name in _listdir(wiki):
        if name.endswith(".md") and name not in ("index.md", "log.md"):
            add("page", name[:-3], os.path.join(layout.WIKI_DIR, name))
    think = kbconfig.think_root(root)
    for dirpath, dirs, files in os.walk(think):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.endswith(".md") and not name.startswith("."):
                full = os.path.join(dirpath, name)
                add("think", os.path.relpath(full, think)[:-3].replace(os.sep, "/"), full)
    sess = os.path.join(root, SESSIONS_REL)
    for name in _listdir(sess):
        if name.endswith(".json") and name.count(".") == 1:        # `<id>.<kind>.json` sidecars are not sessions
            add("chat", name[:-5], os.path.join(SESSIONS_REL, name))
    try:
        store = for_kb(root=root)
        keys = [k for k in store.list(RAW_PREFIX) if k.lower().endswith(RAW_EXTS) and not _skipped(k)]
    except Exception:       # noqa: BLE001 - a connector that cannot list (offline, no auth) leaves raw text out of the index
        keys = []
    for key in keys:
        try:
            m = os.stat(store.cached_path(key)).st_mtime       # a local store answers with the file itself
        except (OSError, StorageError):
            continue
        out[key] = ("raw", key, m)
    return out


def _listdir(d):
    try:
        return sorted(os.listdir(d))
    except OSError:
        return []


def _skipped(key):
    """Hidden files and the images folder (sidecars of pictures) hold no text worth finding."""
    parts = key.split("/")
    return any(p.startswith(".") for p in parts) or "images" in parts[:-1]


def _full(root, path):
    return path if os.path.isabs(path) else os.path.join(root, path)


# ---------- reading one document ----------
def _read(path):
    with open(path, "rb") as f:
        return f.read(MAX_BODY).decode("utf-8", errors="ignore")


def _chat_text(messages):
    out = []
    for m in messages if isinstance(messages, list) else []:
        if isinstance(m, dict):
            c = m.get("content", m.get("text"))
            if isinstance(c, str) and c.strip():
                out.append(c.strip())
            elif isinstance(c, list):
                out.extend(b["text"].strip() for b in c if isinstance(b, dict) and isinstance(b.get("text"), str))
    return "\n\n".join(out)


def _document(root, kind, ident, path):
    """(title, body) of one file, or None when it cannot be read."""
    full = _full(root, path)
    try:
        if kind == "raw":
            text = for_kb(root=root).get(path)[:MAX_BODY].decode("utf-8", errors="ignore")
        elif kind == "chat":
            with open(full, encoding="utf-8") as f:
                doc = json.load(f)
            return str(doc.get("title") or ident), _chat_text(doc.get("messages"))
        else:
            text = _read(full)
    except (OSError, ValueError, StorageError):
        return None
    fm = frontmatter.parse(text)[0] or {}
    body = _FM.sub("", text, count=1)
    if kind == "page":
        return frontmatter.page_title(fm, text, ident), body
    stem = ident.rsplit("/", 1)[-1]
    return (frontmatter.unquote(fm.get("title")) or frontmatter.first_heading(body) or stem), body


# ---------- the database ----------
def _connect(root, create=False):
    path = index_path(root)
    if not create and not os.path.isfile(path):
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.executescript(
        "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);"
        "CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, ref TEXT NOT NULL, title TEXT NOT NULL,"
        " path TEXT NOT NULL UNIQUE, mtime REAL NOT NULL);"
        "CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(title, body, tokenize='unicode61 remove_diacritics 2');")
    row = db.execute("SELECT v FROM meta WHERE k='schema'").fetchone()
    if row and row[0] != SCHEMA:
        db.executescript("DELETE FROM docs; DELETE FROM fts; DELETE FROM meta;")
    db.execute("INSERT OR REPLACE INTO meta VALUES('schema', ?)", (SCHEMA,))
    return db


def _drop(db, path):
    row = db.execute("SELECT id FROM docs WHERE path=?", (path,)).fetchone()
    if row:
        db.execute("DELETE FROM fts WHERE rowid=?", (row[0],))
        db.execute("DELETE FROM docs WHERE id=?", (row[0],))


def _put(db, root, path, kind, ident, mtime):
    _drop(db, path)
    doc = _document(root, kind, ident, path)
    if doc is None:
        return
    title, body = doc
    cur = db.execute("INSERT INTO docs(kind, ref, title, path, mtime) VALUES(?,?,?,?,?)", (kind, ident, title, path, mtime))
    db.execute("INSERT INTO fts(rowid, title, body) VALUES(?,?,?)", (cur.lastrowid, title, body))


def _stamp(db, scan):
    newest = max((m for _k, _i, m in scan.values()), default=0.0)
    db.execute("INSERT OR REPLACE INTO meta VALUES('count', ?)", (str(len(scan)),))
    db.execute("INSERT OR REPLACE INTO meta VALUES('max_mtime', ?)", (repr(newest),))


def _signature(scan):
    return str(len(scan)), repr(max((m for _k, _i, m in scan.values()), default=0.0))


def build(root, rebuild=False):
    """Index everything that changed since the last run (everything when `rebuild` or when there is no index). Returns
    the number of documents indexed now."""
    if rebuild:
        try:
            os.remove(index_path(root))
        except OSError:
            pass
    scan = _scan(root)
    db = _connect(root, create=True)
    try:
        with db:
            known = {p: m for p, m in db.execute("SELECT path, mtime FROM docs")}
            for path in set(known) - set(scan):
                _drop(db, path)
            n = 0
            for path, (kind, ident, mtime) in scan.items():
                if known.get(path) != mtime:
                    _put(db, root, path, kind, ident, mtime)
                    n += 1
            _stamp(db, scan)
        return n
    finally:
        db.close()


def update(root, changed_paths):
    """Re-index only these files (root-relative or absolute; a deleted one leaves the index). Needs an index: with none,
    nothing is done (the first search builds it). Returns the number of files looked at."""
    db = _connect(root)
    if db is None:
        return 0
    wanted = {os.path.abspath(_full(root, p)) for p in changed_paths}
    try:
        scan = _scan(root)
        with db:
            hit = 0
            for path in {*scan, *(r[0] for r in db.execute("SELECT path FROM docs"))}:
                if os.path.abspath(_full(root, path)) not in wanted:
                    continue
                hit += 1
                if path in scan:
                    kind, ident, mtime = scan[path]
                    _put(db, root, path, kind, ident, mtime)
                else:
                    _drop(db, path)
            # stamp only when nothing else is out of date: a partial update must not hide a stale index
            if {p: m for p, m in db.execute("SELECT path, mtime FROM docs")} == {p: v[2] for p, v in scan.items()}:
                _stamp(db, scan)
        return hit
    finally:
        db.close()


def update_quiet(root, changed_paths=None):
    """The writers' hook: never raises. With no paths it syncs everything that changed (still only when an index exists)."""
    try:
        if changed_paths is None:
            if os.path.isfile(index_path(root)):
                build(root)
        else:
            update(root, changed_paths)
    except Exception:       # noqa: BLE001 - a search index must never fail a write
        pass


def is_stale(root):
    """True when there is no index or the files no longer match its stored (count, newest mtime): one stat scan."""
    db = _connect(root)
    if db is None:
        return True
    try:
        have = tuple(r[0] if r else None for r in (db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone() for k in ("count", "max_mtime")))
    finally:
        db.close()
    return have != _signature(_scan(root))


def ensure(root):
    if is_stale(root):
        build(root)


# ---------- querying ----------
def fts_query(text):
    """User text as a safe FTS5 query: words only (quotes, operators, NEAR, column filters and punctuation are dropped),
    each one quoted, the last one a prefix match. None when nothing searchable is left."""
    words = re.findall(r"\w+", text or "", re.UNICODE)
    if not words:
        return None
    return " ".join(f'"{w}"' for w in words[:-1]) + (" " if len(words) > 1 else "") + f'"{words[-1]}"*'


def search(root, q, kinds=None, limit=50):
    """[{kind, id, title, snippet, score, path}] best first (bm25, title weighted over body); [] for no hits or no text."""
    match = fts_query(q)
    if not match:
        return []
    wanted = [k for k in (kinds or KINDS) if k in KINDS]
    if not wanted:
        return []
    ensure(root)
    db = _connect(root)
    if db is None:
        return []
    marks = ",".join("?" * len(wanted))
    try:
        rows = db.execute(
            f"SELECT d.kind, d.ref, d.title, d.path, snippet(fts, 1, '', '', '…', 18), bm25(fts, 6.0, 1.0) AS s "
            f"FROM fts JOIN docs d ON d.id = fts.rowid WHERE fts MATCH ? AND d.kind IN ({marks}) ORDER BY s LIMIT ?",
            (match, *wanted, max(1, int(limit)))).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()
    return [{"kind": k, "id": ref, "title": title, "snippet": " ".join((snip or "").split()), "score": round(-s, 4), "path": path}
            for k, ref, title, path, snip, s in rows]


# ---------- command line ----------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="distill search text", description=__doc__.split("\n\n")[0])
    ap.add_argument("query", nargs="*", help="the words to find (the last one matches as a prefix)")
    ap.add_argument("--kinds", default="", help="comma list of: " + ", ".join(KINDS))
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--rebuild", action="store_true", help="drop the index and build it again")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    from kb_distillery.config.paths import vault_root
    root = vault_root()
    if a.rebuild:
        n = build(root, rebuild=True)
        print(f"indexed {n} documents", file=sys.stderr)
    q = " ".join(a.query)
    if not q:
        return 0 if a.rebuild else 2
    hits = search(root, q, [k for k in a.kinds.split(",") if k] or None, a.limit)
    if a.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    else:
        for h in hits:
            print(f"{h['kind']:5} {h['id']}  {h['title']}\n      {h['snippet']}")
        if not hits:
            print("no matches", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
