"""In-process cache for the graph snapshot: `/api/graph` is instant while nothing changed.

The key is (kb root, layer, view id, relations on); an entry is reused while the **change signature** is the same:
(relpath, mtime_ns, size) of every wiki page, the side files the snapshot reads (kb.toml, aliases, card vectors, and
meta/corpus.tsv for the raw layer), the dates file of a share build, and the git HEAD sha (the page dates come from
history). Any edit, add, delete or commit therefore rebuilds. One lock per key: concurrent callers wait for the
build in flight instead of starting a second one. `KB_GRAPH_CACHE=0` turns the cache off (every call builds).

A hit returns a shallow copy of the cached snapshot (callers add top-level keys such as `kbs`); do not mutate
the nested nodes/links."""
import hashlib
import os
import threading

from kb_distillery.graph import snapshot as _snap

ENV = "KB_GRAPH_CACHE"
_SIDE_FILES = ("kb.toml", os.path.join("meta", "aliases.tsv"), os.path.join(".cache", "vectors.sqlite"))

_entries = {}        # key -> (signature, snapshot)
_locks = {}          # key -> Lock
_guard = threading.Lock()


def enabled():
    return os.environ.get(ENV, "1").strip().lower() not in ("0", "false", "off", "no")


def clear():
    with _guard:
        _entries.clear()


def _stat_part(path):
    try:
        st = os.stat(path)
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return "-"


def _walk_stats(base, root, out):
    try:
        it = os.scandir(base)
    except OSError:
        return
    with it:
        for e in it:
            if e.name.startswith("."):
                continue
            try:
                if e.is_dir(follow_symlinks=True):
                    _walk_stats(e.path, root, out)
                elif e.name.endswith(".md"):
                    st = e.stat()
                    out.append(f"{os.path.relpath(e.path, root)}:{st.st_mtime_ns}:{st.st_size}")
            except OSError:
                continue


def signature(root, layer=None):
    """A hash of everything the snapshot of `root` is derived from (see the module docstring)."""
    parts = []
    _walk_stats(os.path.join(root, "wiki"), root, parts)
    parts.sort()
    for rel in _SIDE_FILES:
        parts.append(f"{rel}:{_stat_part(os.path.join(root, rel))}")
    if layer == "raw":
        parts.append("corpus:" + _stat_part(os.path.join(_snap.ROOT, "meta", "corpus.tsv")))
    dates_file = os.environ.get(_snap.DATES_ENV, "")
    if dates_file:
        parts.append(f"dates:{dates_file}:{_stat_part(dates_file)}")
    parts.append("head:" + _snap.head(root))
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()


def cached_graph_snapshot(layer=None, view=None, relations=None):
    """`build_graph_snapshot` behind the cache (same arguments, same result)."""
    if not enabled():
        return _snap.build_graph_snapshot(layer=layer, view=view, relations=relations)
    root = view.root if view else _snap.ROOT
    rel_on = _snap.relations_on() if relations is None else bool(relations)
    key = (root, layer, getattr(view, "id", None) if view else None, rel_on)
    with _guard:
        lock = _locks.setdefault(key, threading.Lock())
    sig = signature(root, layer)
    with lock:                       # a second caller waits here, then finds the entry the first one stored
        hit = _entries.get(key)
        if hit and hit[0] == sig:
            return dict(hit[1])
        snap = _snap.build_graph_snapshot(layer=layer, view=view, relations=rel_on)
        _entries[key] = (sig, snap)
        return dict(snap)
