"""Favorite pages (meta/favorites.json, one knowledge step per change).

Writes go through `kb_distillery.ops.favorite`, the same functions as `distill ops favorite`. A read-only knowledge base
(`?kb=<other>` in multi-kb mode, or a server with KB_READ_ONLY=1) answers every write with 405. Adding a favorite twice
or removing one that is not marked is a no-op: `ok: false` with a `reason`.
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from kb_distillery.server.models.favorites import FavoriteAddRequest, FavoriteList, FavoriteStep
from kb_distillery.services import favorites as svc
from kb_distillery.vault.favorites import FavoritesError

router = APIRouter(tags=["favorites"])

KB = Query("", description="another knowledge base id (read-only, multi-kb mode); empty = the server's own")


def _error(e: FavoritesError):
    return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/api/favorites", response_model=FavoriteList, summary="Favorite pages (sorted slugs)")
def list_favorites(kb: str = KB):
    try:
        return svc.list_favorites(kb)
    except FavoritesError as e:
        return _error(e)


@router.post("/api/favorites", response_model=FavoriteStep, summary="Mark a page as a favorite (one knowledge step)")
def add_favorite(body: FavoriteAddRequest, kb: str = KB):
    try:
        return svc.add_favorite(body.slug, kb=kb)
    except FavoritesError as e:
        return _error(e)


@router.delete("/api/favorites/{slug}", response_model=FavoriteStep, summary="Unmark a favorite page (one knowledge step)")
def remove_favorite(slug: str, kb: str = KB):
    try:
        return svc.remove_favorite(slug, kb=kb)
    except FavoritesError as e:
        return _error(e)
