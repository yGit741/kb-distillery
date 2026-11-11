"""GET /api/embedding — embedding health, semantic clusters, PCA, pair similarity and the saved names (thin over the
services). GET /api/embedding/pairs — random example pairs in a cosine range.
POST /api/embedding/names — start an LLM run that names the components and clusters (through kb_distillery.llm)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from kb_distillery.server.models.embedding import EmbeddingNamesRequest, EmbeddingPairs, EmbeddingReport
from kb_distillery.server.readonly import refuse_when_read_only
from kb_distillery.services import embedding_names
from kb_distillery.services.embedding import PAIRS_MAX, build_embedding_report, sample_pairs

router = APIRouter(tags=["embedding"])


@router.get("/api/embedding", response_model=EmbeddingReport, summary="Embedding health, clusters, components and names")
def get_embedding():
    return embedding_names.apply(build_embedding_report())


@router.get("/api/embedding/pairs", response_model=EmbeddingPairs, summary="Random page pairs in a cosine range")
def get_pairs(lo: float = Query(-1.0, ge=-1.0, le=1.0), hi: float = Query(1.0, ge=-1.0, le=1.0),
              n: int = Query(8, ge=1, le=PAIRS_MAX), seed: int = Query(0, ge=0)):
    return sample_pairs(lo, hi, n, seed)


@router.post("/api/embedding/names", dependencies=[Depends(refuse_when_read_only)], response_model=EmbeddingReport,
             responses={405: {}, 409: {}, 422: {}}, summary="Start naming the components and clusters with an LLM")
def name_embedding(body: EmbeddingNamesRequest):
    try:
        embedding_names.start(body.backend)
    except embedding_names.NamesError as e:
        raise HTTPException(e.status, e.detail) from None
    return embedding_names.apply(build_embedding_report())
