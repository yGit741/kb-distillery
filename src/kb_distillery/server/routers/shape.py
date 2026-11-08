"""POST /api/graph/shape — free text to a graph view: Cypher plus a style clause."""
from fastapi import APIRouter, Depends, HTTPException

from kb_distillery.graph import shape_translate
from kb_distillery.graph.shape import ShapeError
from kb_distillery.server.models.shape import ShapeRequest, ShapeResponse
from kb_distillery.server.readonly import refuse_when_read_only

router = APIRouter(tags=["graph"])
ERRORS = {400: {"description": "Unknown or unusable LLM backend"},
          422: {"description": "The text could not become a valid view: `detail` says why and what to write instead"},
          502: {"description": "The LLM backend failed"}}


@router.post("/api/graph/shape", dependencies=[Depends(refuse_when_read_only)], response_model=ShapeResponse, responses=ERRORS,
             summary="Turn free text into a graph view: Cypher selection plus style clause")
def post_shape(body: ShapeRequest):
    try:
        return shape_translate.shape(body.text, limit=body.limit, backend=body.backend)
    except ShapeError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from None
