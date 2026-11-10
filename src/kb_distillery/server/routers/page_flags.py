"""Flags on a page: /api/pages/{slug}/flags (mark a span inaccurate, list, count, remove) and `/flags/fix`, which turns
every open flag into one proposal. Thin over `kb_distillery.proposals.flags`."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from kb_distillery.proposals import flags as svc
from kb_distillery.proposals.model import ProposalError
from kb_distillery.server.models.page_flags import (PageFlag, PageFlagCount, PageFlagFixReply, PageFlagFixRequest,
                                                    PageFlagList, PageFlagRemoved, PageFlagRequest)
from kb_distillery.server.readonly import refuse_when_read_only

router = APIRouter(tags=["pages"])
ERRORS = {400: {}, 404: {}, 405: {}, 422: {}, 502: {}}


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except ProposalError as e:
        return JSONResponse({"detail": str(e), **e.extra}, status_code=e.status)


@router.get("/api/pages/{slug}/flags", response_model=PageFlagList, responses=ERRORS, summary="The page's flags")
def list_flags(slug: str):
    return _call(lambda: {"slug": slug, "flags": svc.list_flags(slug)})


@router.get("/api/pages/{slug}/flags/count", response_model=PageFlagCount, responses=ERRORS,
            summary="How many flags are open on the page")
def count(slug: str):
    return _call(svc.count, slug)


@router.post("/api/pages/{slug}/flags", dependencies=[Depends(refuse_when_read_only)], response_model=PageFlag,
             responses=ERRORS, summary="Mark a span of the page as inaccurate")
def add(slug: str, body: PageFlagRequest):
    return _call(svc.add, slug, body.text, body.note, body.block_at)


@router.post("/api/pages/{slug}/flags/fix", dependencies=[Depends(refuse_when_read_only)],
             response_model=PageFlagFixReply, responses=ERRORS,
             summary="Turn every open flag into one proposal that addresses them")
def fix(slug: str, body: PageFlagFixRequest | None = None):
    return _call(svc.fix, slug, backend=body.backend if body else None)


@router.delete("/api/pages/{slug}/flags/{flag_id}", dependencies=[Depends(refuse_when_read_only)], response_model=PageFlagRemoved,
               responses=ERRORS, summary="Remove a flag")
def remove(slug: str, flag_id: str):
    return _call(lambda: (svc.remove(slug, flag_id), {"id": flag_id})[1])
