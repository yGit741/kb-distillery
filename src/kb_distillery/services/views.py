"""Pinned graph views and recent shaping steps for the HTTP routes (`kb_distillery.server.routers.views`).

Reads come from `meta/views.json` / `.local/recent.json` (`kb_distillery.vault.views`). Pinned views are written only
through the ops functions the `distill ops view` CLI calls (`kb_distillery.ops.view`): one knowledge step each, never a
direct VCS call from here. HTTP-free: failures are `ViewsError(status, message)` for the router to relay.

Read-only: the server writes only to the knowledge base it serves. Another knowledge base shown in multi-kb mode
(`?kb=<other id>`, flag `kb-view`) is read, never written, and a server started with `KB_READ_ONLY=1` (a hosted or
share-like deployment) refuses every write of these routes (views and recent steps; other routes do not read it). Both are a 405 with a message.
"""
from __future__ import annotations

import os

from kb_distillery.config.paths import vault_root
from kb_distillery.ops import view as ops_view
from kb_distillery.services import kbview
from kb_distillery.vault import views as vv
from kb_distillery.vault.views import ViewsError

DEFAULT_ROOT = vault_root()
READ_ONLY_ENV = "KB_READ_ONLY"


def read_only_reason(kb=""):
    """Why writes are refused for this request, or None when they are allowed."""
    if os.environ.get(READ_ONLY_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
        return f"this server is read-only ({READ_ONLY_ENV} is set): views cannot be changed here"
    if kb and kb != kbview.active_view().id:
        return f"knowledge base {kb!r} is shown read-only: views can only be changed in the knowledge base this server serves"
    return None


def _root(kb=""):
    """The kb root to read: the served one, or another one in multi-kb mode (404 when unknown or the flag is off)."""
    if not kb:
        return DEFAULT_ROOT
    try:
        v = kbview.view(kb)
    except KeyError:
        raise ViewsError(404, f"unknown knowledge base {kb!r}") from None
    return DEFAULT_ROOT if v.active else v.root


def _writable_root(kb=""):
    reason = read_only_reason(kb)
    if reason:
        raise ViewsError(405, reason)
    return DEFAULT_ROOT


# ---------- pinned views ----------

def list_views(kb=""):
    return {"views": vv.load(_root(kb))}


def pin_view(name, spec=None, view_id=None, kb=""):
    return ops_view.pin(name, spec, view_id=view_id, root=_writable_root(kb))


def unpin_view(view_id, kb=""):
    return ops_view.unpin(view_id, root=_writable_root(kb))


def rename_view(view_id, name, kb=""):
    return ops_view.rename(view_id, name, root=_writable_root(kb))


# ---------- recent steps (local, never committed) ----------

def list_recent():
    return {"recent": vv.load_recent(DEFAULT_ROOT)}


def add_recent(text, spec=None):
    reason = read_only_reason()
    if reason:
        raise ViewsError(405, reason)
    return {"recent": vv.append_recent(DEFAULT_ROOT, text, spec)}


def clear_recent():
    reason = read_only_reason()
    if reason:
        raise ViewsError(405, reason)
    vv.clear_recent(DEFAULT_ROOT)
    return {"recent": []}
