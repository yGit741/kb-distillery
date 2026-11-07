"""Search: full text (tier 2 of the search line: SQLite FTS5 index under the kb's `.cache/search/`, built on first use and kept
fresh by the writers; an empty list when there is nothing to find) and meaning (pages close in meaning to a phrase or a page)."""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from kb_distillery.search import fts
from kb_distillery.server.models.search import SimilarResult, TextSearch
from kb_distillery.services import kbview
from kb_distillery.services import similar as svc

router = APIRouter(tags=["search"])


@router.get("/api/search/text", response_model=TextSearch, summary="Full-text search over pages, think notes, chats and raw text",
            responses={404: {"description": "unknown knowledge base"}})
def search_text(q: str = "", kinds: str = Query("", description="comma list of page, think, chat, raw; empty = all"),
                limit: int = Query(30, ge=1, le=200), kb: str = ""):
    try:
        v = kbview.view(kb or None)
    except KeyError:
        return JSONResponse({"error": "not found"}, status_code=404)
    wanted = [k for k in kinds.split(",") if k.strip()] or None
    try:
        hits = fts.search(v.root, q, [k.strip() for k in wanted] if wanted else None, limit)
    except Exception:       # noqa: BLE001 - an unreadable or locked index is "nothing found", never a 500 under the search line
        hits = []
    return {"query": q, "hits": hits}


@router.get("/api/search/similar", response_model=SimilarResult, summary="Pages close in meaning to a phrase or a page",
            responses={404: {"description": "unknown slug"}, 422: {"description": "neither q nor slug"},
                       503: {"description": "semantic search is off or its service is down"}})
def search_similar(q: str = "", slug: str = "", k: int = 20):
    try:
        return {"hits": svc.similar(q, slug, k)}
    except svc.SimilarError as e:
        return JSONResponse({"detail": e.detail}, status_code=e.status)
