"""/api/pages/{slug}/history|compare|restore: how a page changed, and restore as a proposal. Thin over
`kb_distillery.proposals.history`. Errors are `{"detail": message}` with 400, 404, 405, 409."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from kb_distillery.proposals import history as svc
from kb_distillery.proposals.model import ProposalError
from kb_distillery.server.models.page_history import PageCompare, PageHistory, RestoreRequest, RestoreResult
from kb_distillery.server.readonly import refuse_when_read_only

router = APIRouter(tags=["page-history"])
ERRORS = {400: {}, 404: {}, 405: {}, 409: {}}


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except ProposalError as e:
        return JSONResponse({"detail": str(e), **e.extra}, status_code=e.status)


@router.get("/api/pages/{slug}/history", response_model=PageHistory, responses=ERRORS,
            summary="The versions of one page from the kb's git log, newest first")
def page_history(slug: str):
    return _call(lambda: {"slug": slug, "versions": svc.history(slug)})


@router.get("/api/pages/{slug}/compare", response_model=PageCompare, response_model_by_alias=True, responses=ERRORS,
            summary="Hunks turning version `from` into `to` (a sha, or `working`), as the review screen renders them")
def page_compare(slug: str, from_: str = Query(..., alias="from"), to: str = "working"):
    return _call(svc.compare, slug, from_, to)


@router.post("/api/pages/{slug}/restore", dependencies=[Depends(refuse_when_read_only)], response_model=RestoreResult,
             responses=ERRORS, summary="Restore a version (or chosen blocks of it) as a proposal; the page is not written")
def page_restore(slug: str, body: RestoreRequest):
    return _call(svc.restore, slug, body.sha, body.blocks, body.to)
