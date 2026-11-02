"""Scopes: personal working sets of raw files. Writes are one kb(refine) step each (kb_distillery.services.scopes)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kb_distillery.server.models.scopes import (ScopeDetail, ScopeDuplicateRequest, ScopeList, ScopeResolved,
                                  ScopeResolveRequest, ScopeSaveRequest, ScopeStep)
from kb_distillery.services import scopes as scopes_data

router = APIRouter(tags=["scopes"])


def _error(e: scopes_data.ScopeError):
    return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/api/scopes", response_model=ScopeList, summary="All scopes with coverage")
def list_scopes():
    return scopes_data.list_scopes()


@router.post("/api/scopes", response_model=ScopeStep, summary="Create (create: true) or update a scope")
def save_scope(body: ScopeSaveRequest):
    try:
        return scopes_data.save_scope(body.model_dump())
    except scopes_data.ScopeError as e:
        return _error(e)


@router.post("/api/scopes/resolve", response_model=ScopeResolved, summary="Graph node ids to raw files")
def resolve_scope(body: ScopeResolveRequest):
    try:
        return scopes_data.resolve_nodes(body.nodes)
    except scopes_data.ScopeError as e:
        return _error(e)


@router.get("/api/scopes/{slug}", response_model=ScopeDetail, summary="One scope: rows and projection")
def get_scope(slug: str):
    data = scopes_data.get_scope(slug)
    if data is None:
        return JSONResponse({"error": "unknown scope"}, status_code=404)
    return data


@router.delete("/api/scopes/{slug}", response_model=ScopeStep, summary="Delete a scope and its corpus cells")
def delete_scope(slug: str):
    try:
        return scopes_data.delete_scope({"slug": slug})
    except scopes_data.ScopeError as e:
        return _error(e)


@router.post("/api/scopes/{slug}/duplicate", response_model=ScopeStep, summary="Copy a scope under a new slug")
def duplicate_scope(slug: str, body: ScopeDuplicateRequest):
    try:
        return scopes_data.duplicate_scope({"slug": slug, **body.model_dump()})
    except scopes_data.ScopeError as e:
        return _error(e)
