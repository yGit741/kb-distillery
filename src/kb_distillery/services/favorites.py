"""Favorite pages for the HTTP routes (`kb_distillery.server.routers.favorites`).

Reads come from `meta/favorites.json` (`kb_distillery.vault.favorites`). Writes go only through the ops functions the
`distill ops favorite` CLI calls (`kb_distillery.ops.favorite`): one knowledge step each, never a direct VCS call from
here. HTTP-free: failures are `FavoritesError(status, message)` for the router to relay.

Read-only, exactly like the pinned views: another knowledge base shown in multi-kb mode (`?kb=<other id>`) is read,
never written, and a server started with `KB_READ_ONLY=1` refuses every write. Both are a 405 with a message.
"""
from __future__ import annotations

import os

from kb_distillery.config.paths import vault_root
from kb_distillery.ops import favorite as ops_favorite
from kb_distillery.services import kbview
from kb_distillery.vault import favorites as fv
from kb_distillery.vault.favorites import FavoritesError

DEFAULT_ROOT = vault_root()
READ_ONLY_ENV = "KB_READ_ONLY"


def read_only_reason(kb=""):
    """Why writes are refused for this request, or None when they are allowed."""
    if os.environ.get(READ_ONLY_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
        return f"this server is read-only ({READ_ONLY_ENV} is set): favorites cannot be changed here"
    if kb and kb != kbview.active_view().id:
        return f"knowledge base {kb!r} is shown read-only: favorites can only be changed in the knowledge base this server serves"
    return None


def _root(kb=""):
    if not kb:
        return DEFAULT_ROOT
    try:
        v = kbview.view(kb)
    except KeyError:
        raise FavoritesError(404, f"unknown knowledge base {kb!r}") from None
    return DEFAULT_ROOT if v.active else v.root


def _writable_root(kb=""):
    reason = read_only_reason(kb)
    if reason:
        raise FavoritesError(405, reason)
    return DEFAULT_ROOT


def list_favorites(kb=""):
    return {"slugs": fv.load(_root(kb))}


def add_favorite(slug, kb=""):
    return ops_favorite.add(slug, root=_writable_root(kb))


def remove_favorite(slug, kb=""):
    return ops_favorite.remove(slug, root=_writable_root(kb))
