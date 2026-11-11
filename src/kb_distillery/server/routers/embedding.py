"""GET /api/embedding — embedding health, semantic clusters and the 2D map (thin over the service)."""
from fastapi import APIRouter

from kb_distillery.server.models.embedding import EmbeddingReport
from kb_distillery.services.embedding import build_embedding_report

router = APIRouter(tags=["embedding"])


@router.get("/api/embedding", response_model=EmbeddingReport, summary="Embedding health, clusters and map")
def get_embedding():
    return build_embedding_report()
