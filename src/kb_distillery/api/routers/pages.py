"""Page explorer: index, one page, search, shortest paths, and the images/visualizations pages embed."""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from kb_distillery.api.models.pages import PageDetail, PageIndex, PathResult, SearchResult
from kb_distillery.services import kbview
from kb_distillery.services import pages as svc

router = APIRouter(tags=["pages"])

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".svg": "image/svg+xml", ".webp": "image/webp"}
NOT_FOUND = {"error": "not found"}


@router.get("/api/pages", response_model=PageIndex, summary="Every page as a card, plus links and wanted pages",
            responses={404: {"description": "unknown knowledge base"}})
def list_pages(kb: str = ""):
    try:
        v = kbview.view(kb or None)
    except KeyError:
        return JSONResponse(NOT_FOUND, status_code=404)
    return svc.build_index(None if v.active else v)


@router.get("/api/pages/{slug}", response_model=PageDetail, summary="One page: markdown, backlinks, suggestions",
            responses={404: {"description": "unknown slug"}})
def get_page(slug: str, kb: str = ""):
    try:
        v = kbview.view(kb or None)
    except KeyError:
        return JSONResponse(NOT_FOUND, status_code=404)
    data = svc.build_page(slug, None if v.active else v)
    if data is None:
        return JSONResponse(NOT_FOUND, status_code=404)
    return data


@router.get("/api/search", response_model=SearchResult, summary="Full-text search over the pages")
def search_pages(q: str = "", limit: str = ""):
    return svc.search(q, min(int(limit), 5000) if limit.isdigit() else 40)


@router.get("/api/path", response_model=PathResult, summary="Shortest undirected link paths between two pages",
            responses={404: {"description": "unknown page"}})
def find_path(a: str = "", b: str = ""):
    data = svc.find_paths(a, b)
    if data is None:
        return JSONResponse(NOT_FOUND, status_code=404)
    return data


@router.get("/api/assets/vault", summary="An image a page embeds (resolved under raw/)",
            responses={200: {"content": {"image/*": {}}}, 404: {"description": "no such image"}})
def vault_asset(name: str = ""):
    full = svc.resolve_asset(name)
    if not full:
        raise HTTPException(404)
    return FileResponse(full, media_type=IMAGE_TYPES.get(os.path.splitext(full)[1].lower(),
                                                          "application/octet-stream"))


@router.get("/api/assets/chat", summary="An extracted chat visualization (html/svg/png)",
            responses={200: {"content": {"text/html": {}, "image/svg+xml": {}, "image/png": {}}},
                       404: {"description": "no such asset"}})
def chat_asset(path: str = ""):
    from kb_distillery.dashboard.serve import VIZ_REPORTER      # same height reporter the legacy route injects
    full = svc.resolve_chat_asset(path)
    if not full:
        raise HTTPException(404)
    ext = os.path.splitext(full)[1].lower()
    ctype = {".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}[ext]
    with open(full, "rb") as f:
        body = f.read()
    if ext == ".html":
        body = body.replace(b"</body>", VIZ_REPORTER + b"</body>") if b"</body>" in body else body + VIZ_REPORTER
    return Response(body, media_type=ctype)
