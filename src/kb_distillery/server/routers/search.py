"""Meaning search: pages close in meaning to a phrase (`q`) or to a page (`slug`)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kb_distillery.server.models.search import SimilarResult
from kb_distillery.services import similar as svc

router = APIRouter(tags=["search"])


@router.get("/api/search/similar", response_model=SimilarResult, summary="Pages close in meaning to a phrase or a page",
            responses={404: {"description": "unknown slug"}, 422: {"description": "neither q nor slug"},
                       503: {"description": "semantic search is off or its service is down"}})
def search_similar(q: str = "", slug: str = "", k: int = 20):
    try:
        return {"hits": svc.similar(q, slug, k)}
    except svc.SimilarError as e:
        return JSONResponse({"detail": e.detail}, status_code=e.status)
