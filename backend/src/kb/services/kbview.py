"""A read-only view of any knowledge base the explorer can find, for showing several in one running app.

The server still works on one knowledge base (`kb.paths.KB`): every write, ops session and lint run is on it.
Another knowledge base is only read — its pages, graph and types — so nothing can land in the wrong repo.
`view(None)` and `view(<active id>)` are the active knowledge base; an unknown id is a `KeyError` (→ 404).
Ids are looked up in `kbconfig.discover()`, never joined into a path. Another knowledge base is reachable only
while the runtime flag `kb-view` is on (server side too, so a dark feature serves nothing).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from kb import kbconfig, paths
from kb.core import kbtypes, schema


@dataclass(frozen=True)
class KbView:
    id: str
    name: str
    root: str
    types: kbtypes.Types
    active: bool


FLAG = "kb-view"
_views: dict[str, KbView] = {}


def active_view() -> KbView:
    cfg = paths.KB
    return KbView(id=cfg.id if cfg else "", name=cfg.name if cfg else "Knowledge base",
                  root=paths.ROOT, types=schema._T, active=True)


def view(kb_id: str | None = None) -> KbView:
    act = active_view()
    if not kb_id or kb_id == act.id:
        return act
    from kb.services.pages import _flag_on
    if not _flag_on(FLAG):
        raise KeyError(kb_id)
    try:
        known = kbconfig.discover()
    except kbconfig.KbConfigError:
        raise KeyError(kb_id) from None
    if kb_id not in known:
        raise KeyError(kb_id)
    cached = _views.get(kb_id)
    if cached and cached.root == known[kb_id]:
        return cached
    try:
        cfg = kbconfig.load_dir(known[kb_id], kb_id, strict=False)
    except kbconfig.KbConfigError:
        raise KeyError(kb_id) from None
    v = KbView(id=cfg.id, name=cfg.name, root=cfg.root, types=kbtypes.load(cfg), active=False)
    _views[kb_id] = v
    return v


def head(root: str) -> str:
    """The git HEAD sha of `root` ("" without git): the cache key for anything derived from history."""
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
