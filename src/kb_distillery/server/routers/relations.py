"""GET /api/relations/proposals — every LLM relation proposal, filterable by confidence range and kind (read-only)."""
from fastapi import APIRouter, Query

from kb_distillery.server.models.relations import RelationProposals
from kb_distillery.services import relation_proposals

router = APIRouter(tags=["relations"])


@router.get("/api/relations/proposals", response_model=RelationProposals,
            summary="Relation proposals in a confidence range (0..1), best first")
def get_proposals(min: float = Query(0.0, ge=0.0, le=1.0, description="lowest confidence shown"),
                  max: float = Query(1.0, ge=0.0, le=1.0, description="highest confidence shown"),
                  kind: str | None = Query(None, description="one relation kind, or all")):
    return relation_proposals.query(min, max, kind)
