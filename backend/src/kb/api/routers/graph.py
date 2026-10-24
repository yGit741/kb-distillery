"""GET /api/graph — the wiki link graph; `?layer=raw` merges the private data layer in."""
from fastapi import APIRouter, Query

from kb.api.models.graph import GraphSnapshot
from kb.services.graph import build_graph_snapshot

router = APIRouter(tags=["graph"])


@router.get("/api/graph", response_model=GraphSnapshot, summary="Wiki link graph")
def get_graph(layer: str = Query("", description="`raw` adds the data layer; anything else is ignored")):
    return build_graph_snapshot(layer="raw" if layer == "raw" else None)
