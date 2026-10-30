"""POST /api/graph/cypher, GET /api/graph/queries, POST /api/graph/queries/{name} — read-only graph queries."""
from fastapi import APIRouter, HTTPException

from kb.api.models.cypher import CypherRequest, NamedQuery, NamedQueryRequest, QueryTable
from kb.services import cypher

router = APIRouter(tags=["graph"])
ERRORS = {400: {"description": "Query rejected: `detail` says why and what to use instead"}}


@router.post("/api/graph/cypher", response_model=QueryTable, responses=ERRORS,
             summary="Run a read-only Cypher query (supported subset) on the wiki graph")
def post_cypher(body: CypherRequest):
    try:
        return cypher.run(body.query, limit=body.limit)
    except cypher.QueryError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/api/graph/queries", response_model=list[NamedQuery], summary="Named graph queries")
def get_named_queries():
    return cypher.named_list()


@router.post("/api/graph/queries/{name}", response_model=QueryTable, responses=ERRORS,
             summary="Run a named graph query")
def post_named_query(name: str, body: NamedQueryRequest):
    try:
        return cypher.run_named(name, body.params, limit=body.limit)
    except cypher.QueryError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
