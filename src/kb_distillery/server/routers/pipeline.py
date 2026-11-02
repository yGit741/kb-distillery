"""GET /api/pipeline — ingestion and digestion snapshot (alias /api/digestion stays in the legacy server)."""
from fastapi import APIRouter

from kb_distillery.server.models.pipeline import PipelineSnapshot
from kb_distillery.services import pipeline

router = APIRouter(tags=["pipeline"])


@router.get("/api/pipeline", response_model=PipelineSnapshot, summary="Ingestion and digestion snapshot")
def get_pipeline():
    return pipeline.build_digestion_snapshot()
