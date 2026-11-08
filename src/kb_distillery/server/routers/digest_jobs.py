"""Digest jobs: POST /api/digest/preview (no model call), POST/GET /api/digest/jobs, GET /api/digest/jobs/{id}[/events], DELETE cancels.

A job runs full digests in a worker process, one `kb(digest)` knowledge step per finished source; `/events` streams its
progress over SSE. A read-only server (KB_READ_ONLY=1) answers the job writes with 405, like every other write.
"""
from fastapi import APIRouter, Depends, HTTPException

from kb_distillery.server.models.digest_jobs import DigestJob, DigestJobList, DigestPreview, DigestRequest
from kb_distillery.server.readonly import refuse_when_read_only
from kb_distillery.server.sse import sse_response
from kb_distillery.services import digest_jobs as svc

router = APIRouter(tags=["digest"])
ERRORS = {404: {}, 405: {}, 409: {}, 422: {}}


def _call(fn, *args):
    try:
        return fn(*args)
    except svc.JobError as e:
        raise HTTPException(e.status, e.message) from None


@router.post("/api/digest/preview", response_model=DigestPreview, responses=ERRORS,
             summary="What a digest job would cost and take, on its default backend and on each of the three (no model call)")
def preview(body: DigestRequest):
    return _call(svc.preview, body.raws, body.backend, body.model)


@router.post("/api/digest/jobs", dependencies=[Depends(refuse_when_read_only)], response_model=DigestJob, responses=ERRORS,
             summary="Start a digest job: full digests in a worker, one knowledge step per finished source")
def start(body: DigestRequest):
    return _call(svc.start_job, body.raws, body.backend, body.model)


@router.get("/api/digest/jobs", response_model=DigestJobList, summary="Digest jobs, newest first")
def jobs():
    return {"jobs": svc.list_jobs()}


@router.get("/api/digest/jobs/{job_id}", response_model=DigestJob, responses={404: {}}, summary="One digest job")
def job(job_id: str):
    return _call(svc.get, job_id)


@router.get("/api/digest/jobs/{job_id}/events", responses={404: {}},
            summary="SSE: a `job` event on every change, `end` when the job stops")
def job_events(job_id: str):
    _call(svc.get, job_id)                                   # a 404 before the stream opens
    return sse_response(svc.events(job_id))


@router.delete("/api/digest/jobs/{job_id}", dependencies=[Depends(refuse_when_read_only)], response_model=DigestJob,
               responses=ERRORS, summary="Cancel a digest job: the source in flight rolls back, finished ones stay committed")
def cancel(job_id: str):
    return _call(svc.cancel, job_id)
