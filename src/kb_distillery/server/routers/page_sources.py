"""The raw files, source pages and URLs behind one page (read-only, 0 LLM)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kb_distillery.server.models.page_sources import PageSources
from kb_distillery.services import kbview
from kb_distillery.services import page_sources as svc

router = APIRouter(tags=["pages"])


@router.get("/api/pages/{slug}/sources", response_model=PageSources,
            summary="The sources behind one page: title, format, disposition and where the page cites them",
            responses={404: {"description": "unknown slug or knowledge base"}})
def get_page_sources(slug: str, kb: str = ""):
    try:
        v = kbview.view(kb or None)
    except KeyError:
        return JSONResponse({"error": "not found"}, status_code=404)
    data = svc.build_sources(slug, None if v.active else v)
    if data is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return data
