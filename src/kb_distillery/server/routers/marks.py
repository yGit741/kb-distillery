"""Unsure-formula marks on wiki pages (`[!](mark:<sha12>/p0188/3)`): read one, its crop, mark it correct, ask for a fix, apply it.

Resolve and apply are one `kb(refine)` knowledge step each; fix calls a model and writes nothing. A read-only kb refuses
the writes (403 app-wide, 405 under KB_READ_ONLY=1, like every other write).
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from kb_distillery.server.models.marks import (MarkApplyRequest, MarkDetail, MarkFixReply, MarkFixRequest,
                                               MarkResolveRequest, MarkStepResult)
from kb_distillery.server.readonly import refuse_when_read_only
from kb_distillery.services import marks as svc

router = APIRouter(tags=["marks"])
ERRORS = {403: {}, 404: {}, 405: {}, 409: {}, 422: {}, 502: {}}
BASE = "/api/marks/{sha12}/{page}/{mark_id}"


def _call(fn, *a):
    try:
        return fn(*a)
    except svc.MarkError as e:
        raise HTTPException(e.status, e.message) from None


@router.get(BASE, response_model=MarkDetail, responses=ERRORS, summary="One unsure-formula mark: its record, crop url and resolution")
def get_mark(sha12: str, page: str, mark_id: int):
    return _call(svc.lookup, sha12, page, mark_id)


@router.get(BASE + "/crop", responses={404: {}, 200: {"content": {"image/png": {}}}},
            summary="The crop of the original page the mark sits in (PNG)")
def get_crop(sha12: str, page: str, mark_id: int):
    return FileResponse(_call(svc.crop_file, sha12, page, mark_id), media_type="image/png")


@router.post(BASE + "/resolve", dependencies=[Depends(refuse_when_read_only)], response_model=MarkStepResult, responses=ERRORS,
             summary="Correct as is: remove the mark link from the page, keep the formula (one knowledge step)")
def resolve(sha12: str, page: str, mark_id: int, body: MarkResolveRequest):
    return _call(svc.resolve, sha12, page, mark_id, body.slug)


@router.post(BASE + "/fix", dependencies=[Depends(refuse_when_read_only)], response_model=MarkFixReply, responses=ERRORS,
             summary="Fix me: ask a model for the corrected formula (nothing is saved)")
def fix(sha12: str, page: str, mark_id: int, body: MarkFixRequest):
    """One `kb_distillery.llm` request with the crop image. Backend: `backend`, else $KB_LLM_BACKEND, else subscription;
    all three work, but `batch` is a poor fit for an interactive call: it can take minutes and gives up after 10."""
    return _call(svc.fix, sha12, page, mark_id, body.slug, body.instruction, body.backend)


@router.post(BASE + "/apply", dependencies=[Depends(refuse_when_read_only)], response_model=MarkStepResult, responses=ERRORS,
             summary="Approve a fix: replace the formula the mark follows and remove the mark (one knowledge step)")
def apply(sha12: str, page: str, mark_id: int, body: MarkApplyRequest):
    return _call(svc.apply, sha12, page, mark_id, body.slug, body.replacement)
