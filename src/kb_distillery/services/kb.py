"""The knowledge base behind this app (`/api/kb`) and every one the explorer can see (`/api/kb/list`).

Facts only, read from kb.toml, the folder and its git repo. The one write is the star set: the ids the user starred,
in `<bases dir>/.stars.json` (a dotfile, so discovery skips it; never inside a kb). Switching the active knowledge
base is a relaunch (`distill launch --kb <id|path>`): ROOT is resolved when the process starts.
"""
import contextlib
import fcntl
import json
import os
import subprocess
import tempfile
import threading

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import paths
from kb_distillery.vault import schema
from kb_distillery.vault.digest import instruction_files


def _git(root, *args):
    try:
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=False, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def git_state(root):
    """{repo, branch, last_tag, dirty} for a folder; repo False (and the rest empty) when it is not a git repo."""
    if not os.path.exists(os.path.join(root, ".git")):
        return {"repo": False, "branch": "", "last_tag": "", "dirty": 0}
    tags = _git(root, "for-each-ref", "--sort=-creatordate", "--format=%(refname:short)", "--count=1", "refs/tags/kb-*")
    porcelain = _git(root, "status", "--porcelain", "--untracked-files=all")
    return {"repo": True, "branch": _git(root, "symbolic-ref", "--short", "-q", "HEAD"),
            "last_tag": tags, "dirty": len([l for l in porcelain.splitlines() if l.strip()])}


def _types():
    return [{"id": t, "label": schema.TYPE_LABEL[t], "layer": schema.LAYER_OF[t], "prefix": schema.SLUG_PREFIX.get(t, ""),
             "color": schema.TYPE_COLOR[t], "maturities": sorted(schema.TYPE_STATUS[t])} for t in schema.TYPE_ORDER]


def _meta_overrides(root):
    """Which of the explorer's src/kb_distillery/kits/base/defaults this knowledge base overrides with its own meta/<x>."""
    out = [name for name in ("flags.toml", "templates", "docs") if os.path.exists(os.path.join(root, "meta", name))]
    if os.path.isdir(os.path.join(root, "digest")):
        out.append("digest")
    return out


def active():
    from kb_distillery.config.flags.registry import FLAGS_SOURCE
    cfg = paths.KB
    root = paths.ROOT
    return {
        "id": cfg.id if cfg else None, "name": cfg.name if cfg else "No knowledge base selected",
        "root": root, "read_only": kbconfig.is_read_only(root), "config": cfg.path if cfg else None,
        "schema_version": ".".join(map(str, cfg.schema_version if cfg else schema.SCHEMA_VERSION)),
        "git": git_state(root),
        "think_root": paths.THINK_PATH, "think_git": git_state(paths.THINK_PATH),
        "types": _types(), "areas": sorted(schema.TOPIC_SLUGS), "source_fields": list(schema.SOURCE_FIELDS),
        "digest": [{"part": part, "origin": origin, "path": path} for part, (path, origin) in instruction_files().items()],
        "flags_registry": FLAGS_SOURCE, "meta_overrides": _meta_overrides(root),
        "bases_dir": kbconfig.bases_dir(),
        "relaunch": "distill launch --kb <id|path>",
    }


STARS_FILE = ".stars.json"


def _stars_path():
    return os.path.join(kbconfig.bases_dir(), STARS_FILE)


def stars() -> set[str]:
    """The starred ids; empty when the file is missing or unreadable."""
    try:
        with open(_stars_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    return {s for s in data if isinstance(s, str)} if isinstance(data, list) else set()


_STARS_LOCK = threading.Lock()


def set_star(kb_id: str, starred: bool) -> set[str]:
    """Star (or unstar) `kb_id` -> the new star set. An id that is no longer discovered is kept: it may come back."""
    # FastAPI runs sync routes in a thread pool, and several app instances may share one bases dir: the thread lock
    # and a file lock beside the stars keep two stars at once from losing one
    path = _stars_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _STARS_LOCK, open(path + ".lock", "a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ids = stars()
        if starred:
            ids.add(kb_id)
        else:
            ids.discard(kb_id)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=STARS_FILE, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(sorted(ids), f, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        return ids


def listing():
    rows = []
    starred = stars()
    for kb_id, root in kbconfig.discover().items():
        row = {"id": kb_id, "root": root, "name": "", "schema_version": "", "error": "", "git": git_state(root),
               "active": bool(paths.KB and os.path.realpath(paths.KB.root) == os.path.realpath(root)),
               "starred": kb_id in starred}
        try:
            cfg = kbconfig.load_dir(root, kb_id)
            row["name"], row["schema_version"] = cfg.name, ".".join(map(str, cfg.schema_version))
        except kbconfig.KbConfigError as e:
            row["error"] = str(e)
        rows.append(row)
    return {"bases_dir": kbconfig.bases_dir(),
            "think_root": paths.THINK_PATH, "active": paths.KB.id if paths.KB else None, "kbs": rows}


# (kb id, folder) -> (signature of the folder when counted, graph_stats or None when its graph would not build)
_SIZES: dict[tuple[str, str], tuple[str, dict | None]] = {}
_SIZES_LOCK = threading.Lock()
_PENDING: dict[tuple[str, str], None] = {}      # waiting for the worker, in order
_COUNTING: set[tuple[str, str]] = set()          # the one the worker is counting now (never queued twice)
_SIZES_WORKER: threading.Thread | None = None


def _size_of(kb_id, root):
    """(signature, graph_stats) of one knowledge base, built from its (cached) graph snapshot; stats None when its graph
    does not build (remembered with the signature, so it is not retried until the folder changes)."""
    from kb_distillery.graph.cache import cached_graph_snapshot, signature
    from kb_distillery.graph.stats import graph_stats
    from kb_distillery.services import kbview
    sig = signature(root)
    try:
        v = kbview.view(kb_id)
        return sig, graph_stats(cached_graph_snapshot(view=None if v.active else v))
    except Exception:                # noqa: BLE001 — a broken knowledge base must not hide the others' sizes
        return sig, None


def _drain():
    """The worker: count every queued knowledge base, including ones queued while it runs."""
    while True:
        with _SIZES_LOCK:
            if not _PENDING:
                return
            key = next(iter(_PENDING))
            del _PENDING[key]
            _COUNTING.add(key)
        try:
            got = _size_of(*key)
        finally:
            with _SIZES_LOCK:
                _COUNTING.discard(key)
        with _SIZES_LOCK:
            _SIZES[key] = got


def graph_sizes(wait=False):
    """{"kbs": {id: graph_stats}, "pending": [id]} for every knowledge base whose graph this app can show.

    A size is kept per knowledge base with the signature of its folder (graph/cache.py). One not counted yet, or
    whose folder changed, is queued for one background thread and listed in `pending`; a changed one keeps its last
    size meanwhile, so the menu never loses a row's count. One whose graph does not build is left out and not
    retried until its folder changes. The request never builds a graph itself; the header menu asks again while
    `pending` is not empty. `wait=True` drains the queue in the request (tests)."""
    global _SIZES_WORKER
    from kb_distillery.graph.cache import signature
    from kb_distillery.services import kbview
    act = kbview.active_view()
    out, pending = {}, []
    for kb_id in dict.fromkeys(k for k in [act.id, *kbconfig.discover()] if k):
        try:
            root = os.path.realpath(kbview.view(kb_id).root)
            sig = signature(root)
        except Exception:            # noqa: BLE001 — an id that no longer resolves
            continue
        key = (kb_id, root)
        with _SIZES_LOCK:
            hit = _SIZES.get(key)
            if hit is None or hit[0] != sig:
                if key not in _COUNTING:
                    _PENDING[key] = None
                pending.append(kb_id)
        if hit is not None and hit[1] is not None:
            out[kb_id] = hit[1]               # the last size, also while a changed folder is counted again
    if pending and wait:
        if _SIZES_WORKER is not None:
            _SIZES_WORKER.join()
        _drain()
        return graph_sizes()
    if pending:
        with _SIZES_LOCK:
            if _SIZES_WORKER is None or not _SIZES_WORKER.is_alive():
                _SIZES_WORKER = threading.Thread(target=_drain, name="kb-sizes", daemon=True)
                _SIZES_WORKER.start()
    return {"kbs": out, "pending": pending}
