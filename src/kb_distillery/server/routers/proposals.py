"""Agent proposals: /api/proposals. An agent change to the wiki is a proposal the owner reviews hunk by hunk, then applies
as one knowledge step. Thin over `kb_distillery.proposals.service`; a read-only server (KB_READ_ONLY=1) answers every
write with 405. Errors are `{"detail": message, ...}` with 400, 404, 405, 409 (stale / not open), 422 (blocking checks).
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from kb_distillery.proposals import service as svc
from kb_distillery.proposals.model import ProposalError
from kb_distillery.server.models.proposals import (ApplyResult, DecisionRequest, Proposal, ProposalCreate, ProposalList,
                                                   ProposalRender, RejectRequest, RevisionCreate)
from kb_distillery.server.readonly import refuse_when_read_only

router = APIRouter(tags=["proposals"])
ERRORS = {400: {}, 404: {}, 405: {}, 409: {}, 422: {}}
WRITE = [Depends(refuse_when_read_only)]


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except ProposalError as e:
        return JSONResponse({"detail": str(e), **e.extra}, status_code=e.status)


def _ops(ops):
    return [o.model_dump(exclude_none=True) for o in ops]


@router.get("/api/proposals", response_model=ProposalList, summary="Proposals, newest first (optionally one status)")
def list_proposals(status: str | None = Query(None, description="open | applied | rejected | stale")):
    return _call(lambda: {"proposals": svc.list_proposals(status)})


@router.post("/api/proposals", dependencies=WRITE, response_model=Proposal, responses=ERRORS,
             summary="Create a proposal (revision 1): hunks and tier-1 checks computed here")
def create(body: ProposalCreate):
    return _call(svc.create, body.title, _ops(body.ops), body.producer.model_dump(), body.note)


@router.get("/api/proposals/{pid}", response_model=Proposal, responses=ERRORS,
            summary="One proposal: current revision's hunks, decisions, checks, stale recomputed")
def get(pid: str):
    return _call(svc.get, pid)


@router.post("/api/proposals/{pid}/revisions", dependencies=WRITE, response_model=Proposal, responses=ERRORS,
             summary="A new revision; decisions survive for hunks whose before/after are unchanged")
def revise(pid: str, body: RevisionCreate):
    return _call(svc.revise, pid, _ops(body.ops), body.note)


@router.post("/api/proposals/{pid}/decisions", dependencies=WRITE, response_model=Proposal, responses=ERRORS,
             summary="Accept, reject or correct one hunk ({hunk_id, decision}) or several ({decisions: [...]})")
def decide(pid: str, body: DecisionRequest):
    if body.decisions is not None:
        items = [d.model_dump() for d in body.decisions]
    elif body.hunk_id and body.decision:
        items = [{"hunk_id": body.hunk_id, "decision": body.decision, "comment": body.comment}]
    else:
        return JSONResponse({"detail": "give {hunk_id, decision} or {decisions: [...]}"}, status_code=400)
    return _call(svc.decide, pid, items)


@router.post("/api/proposals/{pid}/apply", dependencies=WRITE, response_model=ApplyResult, responses=ERRORS,
             summary="Apply the accepted hunks as one knowledge step (409 stale, 422 blocking checks)")
def apply(pid: str):
    return _call(svc.apply, pid)


@router.post("/api/proposals/{pid}/reject", dependencies=WRITE, response_model=Proposal, responses=ERRORS,
             summary="Reject the whole proposal (kept on disk with its reason)")
def reject(pid: str, body: RejectRequest | None = None):
    return _call(svc.reject, pid, body.reason if body else None)


@router.get("/api/proposals/{pid}/render", response_model=ProposalRender, responses=ERRORS,
            summary="Each touched page as it is now, with the hunks positioned by block index")
def render(pid: str):
    return _call(svc.render, pid)
