"""Ingest from the app: POST /api/ingest (a file or a URL), GET /api/ingest (the list), GET /api/ingest/{job_id}[/events].

The job saves the source under raw/, reads it through `kb_distillery.llm` and ends in ONE proposal (producer kind `ingest`)
with the new pages; it never writes `wiki/`. A read-only server (KB_READ_ONLY=1) answers the POST with 405.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from kb_distillery.server.models.ingest_ui import IngestJob, IngestListItem, IngestStarted, IngestUrlRequest
from kb_distillery.server.readonly import refuse_when_read_only
from kb_distillery.server.sse import sse_response
from kb_distillery.services import ingest_ui as svc

router = APIRouter(tags=["ingest"])
ERRORS = {404: {}, 405: {}, 413: {}, 415: {}, 422: {}}


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except svc.IngestError as e:
        raise HTTPException(e.status, e.message) from None


@router.post("/api/ingest", dependencies=[Depends(refuse_when_read_only)], response_model=IngestStarted, responses=ERRORS,
             summary="Start an ingest job: multipart `file` (+ tier, collection, backend) or JSON {url, tier, collection, backend}",
             openapi_extra={"requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"url": {"type": "string"}, "tier": {"type": "string"}, "collection": {"type": "string"}, "backend": {"type": "string"}}}},
                                                         "multipart/form-data": {"schema": {"type": "object"}}}}})
async def start(request: Request):
    ctype = (request.headers.get("content-type") or "").lower()
    if ctype.startswith("multipart/"):
        form = await request.form()
        up = form.get("file")
        if up is None or not hasattr(up, "read"):
            raise HTTPException(422, "attach a file as the `file` field, or send JSON with a url")
        data = await up.read()
        return _call(svc.start_file, up.filename or "", data, form.get("tier"), form.get("collection"), form.get("backend") or None)
    try:
        body = IngestUrlRequest.model_validate(await request.json())
    except Exception:                                                        # noqa: BLE001 - malformed JSON / fields
        raise HTTPException(422, "send multipart with a `file`, or JSON {\"url\": ...}") from None
    return _call(svc.start_url, body.url, body.tier, body.collection, body.backend)


@router.get("/api/ingest", response_model=list[IngestListItem],
            summary="The ingest jobs of this kb, newest first (the last 200), each with its proposal's current status")
def jobs():
    return svc.listing()


@router.get("/api/ingest/{job_id}", response_model=IngestJob, responses={404: {}}, summary="One ingest job")
def job(job_id: str):
    return _call(svc.get, job_id)


@router.get("/api/ingest/{job_id}/events", responses={404: {}},
            summary="SSE: a `job` event on every change, `end` when the job stops")
def job_events(job_id: str):
    _call(svc.get, job_id)
    return sse_response(svc.events(job_id))
