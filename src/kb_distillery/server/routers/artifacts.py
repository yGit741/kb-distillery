"""GET /api/artifacts: the artifact layer (artifacts/graph.json plus which page cites which fact) of a knowledge base."""
from fastapi import APIRouter, HTTPException

from kb_distillery.server.models.artifacts import ArtifactGraph
from kb_distillery.services import artifacts, kbview

router = APIRouter(tags=["graph"])


@router.get("/api/artifacts", response_model=ArtifactGraph, responses={404: {"description": "unknown kb, or the kb has no artifact layer"}},
            summary="The artifact layer a builder wrote (nodes, links, views, fact cards) with the pages' cited facts")
def get_artifacts(kb: str | None = None):
    try:
        root = kbview.view(kb or None).root
    except KeyError as e:
        raise HTTPException(404, f"unknown knowledge base {e.args[0]!r}") from None
    data = artifacts.load(root)
    if data is None:
        raise HTTPException(404, "this knowledge base has no artifact layer (artifacts/graph.json)")
    return data
