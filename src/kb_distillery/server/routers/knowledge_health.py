"""GET /api/health/knowledge — anomaly groups over the wiki graph, computed on each request, read-only."""
from fastapi import APIRouter, Query

from kb_distillery.server.models.knowledge_health import KnowledgeHealth
from kb_distillery.services import knowledge_health

router = APIRouter(tags=["health"])


@router.get("/api/health/knowledge", response_model=KnowledgeHealth, summary="Knowledge health: anomaly groups")
def get_knowledge_health(
        min_jaccard: float = Query(knowledge_health.DEFAULT_MIN_JACCARD, ge=0, le=1,
                                   description="missing_links: minimum Jaccard over linked source pages"),
        limit: int = Query(knowledge_health.DEFAULT_LIMIT, ge=0, le=1000,
                           description="items per group; `count` stays the full count")):
    return knowledge_health.build(min_jaccard, limit)
