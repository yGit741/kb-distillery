"""In-process cache for the graph snapshot: `/api/graph` is instant while nothing changed.

The key is (kb root, layer, view id, relations on); an entry is reused while the **change signature** is the same:
(relpath, mtime_ns, size) of every wiki page, the side files the snapshot reads (kb.toml, aliases, card vectors, and
meta/corpus.tsv for the raw layer), the dates file of a share build, and the git HEAD sha (the page dates come from
history). Any edit, add, delete or commit therefore rebuilds. One lock per key: concurrent callers wait for the
build in flight instead of starting a second one. `KB_GRAPH_CACHE=0` turns the cache off (every call builds).

The real server process (`python -m kb_distillery.server`) calls `start_refresher()`: one daemon thread builds the
default snapshots (own kb, with and without the raw layer) at start and re-checks the signature every
`KB_GRAPH_WARM_INTERVAL` seconds (default 30), rebuilding when it changed, so the first request after a long idle
is a hit. `KB_GRAPH_WARM=0` turns it off; nothing else starts it (tests, share builds).

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


WARM_ENV = "KB_GRAPH_WARM"
WARM_INTERVAL_ENV = "KB_GRAPH_WARM_INTERVAL"
_WARM_LAYERS = (None, "raw")
_refresher = None    # (thread, stop event)


def warm_enabled():
    return enabled() and os.environ.get(WARM_ENV, "1").strip().lower() not in ("0", "false", "off", "no")


def warm():
    """Bring the default snapshots of the active kb up to date (a build only when missing or stale)."""
    for layer in _WARM_LAYERS:
        cached_graph_snapshot(layer=layer)


def _interval():
    try:
        return max(0.05, float(os.environ.get(WARM_INTERVAL_ENV, "30")))
    except ValueError:
        return 30.0


def start_refresher(interval=None):
    """Start the warm-up and refresh thread once; returns it, or None when `KB_GRAPH_WARM=0` / the cache is off."""
    global _refresher
    if not warm_enabled():
        return None
    with _guard:
        if _refresher and _refresher[0].is_alive():
            return _refresher[0]
        every = interval if interval is not None else _interval()
        stop = threading.Event()

        def run():
            while True:
                try:
                    warm()
                except Exception:        # a half-written page or a broken kb must not kill the refresher
                    pass
                if stop.wait(every):
                    return

        thread = threading.Thread(target=run, name="graph-warm", daemon=True)
        _refresher = (thread, stop)
        thread.start()
        return thread


def stop_refresher():
    global _refresher
    with _guard:
        cur, _refresher = _refresher, None
    if cur:
        cur[1].set()
        cur[0].join(timeout=30)
