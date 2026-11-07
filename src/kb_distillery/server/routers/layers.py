"""POST /api/graph/layers — a `>` sentence the rules parser could not read, as layer objects (never Cypher)."""
from fastapi import APIRouter, HTTPException

from kb_distillery.graph import layers_translate
from kb_distillery.graph.layers_translate import LayersError
from kb_distillery.server.models.layers import LayersRequest, LayersResponse

router = APIRouter(tags=["graph"])
ERRORS = {400: {"description": "Unknown or unusable LLM backend"},
          422: {"description": "The model's answer was not a valid list of layers: `detail` says why and quotes the answer"},
          502: {"description": "The LLM backend failed"}}


@router.post("/api/graph/layers", response_model=LayersResponse, response_model_exclude_none=True, responses=ERRORS,
             summary="Turn free text into layer objects (show, hide, style) through the shared LLM tool")
def post_layers(body: LayersRequest):
    try:
        vocab = layers_translate.vocabulary()
        return layers_translate.translate(body.text, vocabulary=vocab, backend=body.backend, fallback=body.fallback,
                                          op=body.op)
    except LayersError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from None
