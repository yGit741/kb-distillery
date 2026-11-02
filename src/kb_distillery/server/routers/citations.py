"""GET /api/citations: who cites whom among the cataloged papers (from .cache/citations.json)."""
from fastapi import APIRouter

from kb_distillery.server.models.citations import CitationGraph
from kb_distillery.services import corpus

router = APIRouter(tags=["citations"])


@router.get("/api/citations", response_model=CitationGraph, summary="Citation graph among cataloged papers")
def get_citations():
    return corpus.build_citations()
