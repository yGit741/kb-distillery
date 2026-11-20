"""The Review deck: /api/review. One card per hunk of every open proposal; the deck's decisions are applied in one
batch; a card is rewritten from one owner sentence; a page is split where the model suggests.
Thin over `kb_distillery.proposals.review`; errors are `{"detail": message, ...}` like /api/proposals.
"""
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from kb_distillery.proposals import review as svc
from kb_distillery.proposals.model import ProposalError
from kb_distillery.server.models.base import ApiModel
from kb_distillery.server.models.proposals import Backend
from kb_distillery.server.readonly import refuse_when_read_only

router = APIRouter(tags=["review"])
ERRORS = {400: {}, 404: {}, 405: {}, 409: {}, 422: {}, 502: {}}
WRITE = [Depends(refuse_when_read_only)]


class CardDecision(ApiModel):
    hunk_id: str
    decision: Literal["accept", "reject"]


class BatchItem(ApiModel):
    proposal_id: str
    decisions: list[CardDecision] = []


class ApplyBatch(ApiModel):
    items: list[BatchItem]


class RewriteRequest(ApiModel):
    instruction: str
    backend: Backend | None = None
    marks: list[str] = []           # passages the owner highlighted on the card
    pages: list[str] = []           # page slugs picked in the blast-radius graph


class SplitSuggest(ApiModel):
    slug: str
    hint: str | None = None
    backend: Backend | None = None


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except ProposalError as e:
        return JSONResponse({"detail": str(e), **e.extra}, status_code=e.status)


@router.get("/api/review/deck", summary="The Review deck: one card per hunk of every open proposal")
def deck():
    return _call(svc.deck)


@router.post("/api/review/apply", dependencies=WRITE, responses=ERRORS,
             summary="Record the deck's decisions per proposal, then apply, reject or leave each waiting")
def apply(body: ApplyBatch):
    return _call(svc.apply_batch, [i.model_dump() for i in body.items])


@router.post("/api/review/{pid}/hunks/{hid}/rewrite", dependencies=WRITE, responses=ERRORS,
             summary="A new revision in which only this card's text follows the owner's sentence (one model call)")
def rewrite(pid: str, hid: str, body: RewriteRequest):
    return _call(svc.rewrite, pid, hid, body.instruction, backend=body.backend, marks=body.marks, pages=body.pages)


@router.post("/api/review/{pid}/revert", dependencies=WRITE, responses=ERRORS,
             summary="Back to the previous revision of a proposal (as a new revision)")
def revert(pid: str):
    return _call(svc.revert, pid)


@router.post("/api/review/split", dependencies=WRITE, responses=ERRORS,
             summary="Split a page where the model suggests; the parts arrive as a restructure proposal")
def split(body: SplitSuggest):
    return _call(svc.split, body.slug, body.hint, backend=body.backend)
