"""Pinned graph views (meta/views.json, one knowledge step per change) and recent shaping steps (.local/, never committed).

Writes go through `kb_distillery.ops.view`, the same functions as `distill ops view`. A read-only knowledge base
(`?kb=<other>` in multi-kb mode, or a server with KB_READ_ONLY=1) answers every write with 405.
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from kb_distillery.server.models.views import (RecentAppendRequest, RecentList, ViewList, ViewPinRequest,
                                               ViewRenameRequest, ViewStep)
from kb_distillery.services import views as svc
from kb_distillery.vault.views import ViewsError

router = APIRouter(tags=["views"])

KB = Query("", description="another knowledge base id (read-only, multi-kb mode); empty = the server's own")


def _error(e: ViewsError):
    return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/api/views", response_model=ViewList, summary="Pinned graph views")
def list_views(kb: str = KB):
    try:
        return svc.list_views(kb)
    except ViewsError as e:
        return _error(e)


@router.post("/api/views", response_model=ViewStep, summary="Pin a view (one knowledge step)")
def pin_view(body: ViewPinRequest, kb: str = KB):
    try:
        return svc.pin_view(body.name, body.spec, view_id=body.id, kb=kb)
    except ViewsError as e:
        return _error(e)


@router.patch("/api/views/{view_id}", response_model=ViewStep, summary="Rename a pinned view (one knowledge step)")
def rename_view(view_id: str, body: ViewRenameRequest, kb: str = KB):
    try:
        return svc.rename_view(view_id, body.name, kb=kb)
    except ViewsError as e:
        return _error(e)


@router.delete("/api/views/{view_id}", response_model=ViewStep, summary="Unpin a view (one knowledge step)")
def unpin_view(view_id: str, kb: str = KB):
    try:
        return svc.unpin_view(view_id, kb=kb)
    except ViewsError as e:
        return _error(e)


@router.get("/api/recent", response_model=RecentList, summary="Recent shaping steps (local, oldest first)")
def list_recent():
    return svc.list_recent()


@router.post("/api/recent", response_model=RecentList, summary="Append a recent step (keeps the last 20)")
def add_recent(body: RecentAppendRequest):
    try:
        return svc.add_recent(body.text, body.spec)
    except ViewsError as e:
        return _error(e)


@router.delete("/api/recent", response_model=RecentList, summary="Clear the recent steps")
def clear_recent():
    try:
        return svc.clear_recent()
    except ViewsError as e:
        return _error(e)
