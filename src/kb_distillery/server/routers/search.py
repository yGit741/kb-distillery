"""Tier 2 of the search line: full text over pages, think notes, chats and extracted raw text (SQLite FTS5 index under
the kb's `.cache/search/`, built on first use and kept fresh by the writers). Reads only; an empty list when there is
nothing to find."""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from kb_distillery.search import fts
from kb_distillery.server.models.search import TextSearch
from kb_distillery.services import kbview

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
