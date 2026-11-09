"""In-process cache for the graph snapshot: `/api/graph` is instant while nothing changed.

The key is (kb root, layer, view id, relations on); an entry is reused while the **change signature** is the same:
(relpath, mtime_ns, size) of every wiki page, the side files the snapshot reads (kb.toml, aliases, card vectors, and
meta/corpus.tsv for the raw layer), the dates file of a share build, and the git HEAD sha (the page dates come from
history). Any edit, add, delete or commit therefore rebuilds. One lock per key: concurrent callers wait for the
build in flight instead of starting a second one. `KB_GRAPH_CACHE=0` turns the cache off (every call builds).

A hit returns a shallow copy of the cached snapshot (callers add top-level keys such as `kbs`); do not mutate
the nested nodes/links."""
import datetime
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
        _memos.clear()


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
                if e.is_dir(follow_symlinks=False):
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
        parts.append("corpus:" + _stat_part(os.path.join(root, "meta", "corpus.tsv")))
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


def _tree_stats(base, root, content=False):
    """Hash of (relpath, mtime_ns, size) of every non-hidden file under `base` (any extension). With `content`, the
    file bytes stand in for mtime: the lint rewrites some meta files with the same bytes, which is no change."""
    out = []
    stack = [base]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    else:
                        st = e.stat()
                        if content and st.st_size < 8_000_000:
                            with open(e.path, "rb") as f:
                                mark = hashlib.sha1(f.read()).hexdigest()
                        else:
                            mark = str(st.st_mtime_ns)
                        out.append(f"{os.path.relpath(e.path, root)}:{mark}:{st.st_size}")
                except OSError:
                    continue
    out.sort()
    return hashlib.sha1("\n".join(out).encode()).hexdigest()


def full_signature(root, extra=()):
    """`signature` plus every file under raw/, meta/ and think/, today's date (flag expiry), the root-level files (what a whole-vault pass such as the
    health lint reads) and the stats of the `extra` files. For results derived from more than the wiki graph."""
    parts = [signature(root), _tree_stats(os.path.join(root, "raw"), root),
             _tree_stats(os.path.join(root, "meta"), root, content=True),
             _tree_stats(os.path.join(root, "think"), root), datetime.date.today().isoformat()]
    try:
        parts.append(",".join(sorted(f"{e.name}:{_stat_part(e.path)}" for e in os.scandir(root) if e.is_file())))
    except OSError:
        pass
    parts += [f"{x}:{_stat_part(x)}" for x in extra]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


_memos = {}          # name -> (signature, value, built at)
_memo_lock = threading.Lock()


def memo(name, sig_fn, build):
    """`build()` once per change signature `sig_fn()`; concurrent callers wait for the build in flight.
    `KB_GRAPH_CACHE=0` disables it."""
    if not enabled():
        return build()
    sig = sig_fn()
    with _memo_lock:
        hit = _memos.get(name)
        if hit and hit[0] == sig:
            return hit[1]
        value = build()
        _memos[name] = (sig, value)
        return value
