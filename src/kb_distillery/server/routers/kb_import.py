"""POST /api/kb/import/validate (dry run) and POST /api/kb/import: a new knowledge base from an OKF bundle.

The body is a multipart upload (`file` = a .zip, optional `id`, `kit` fields) or JSON `{git_url, id?, kit?}`. An
upload is held in a temp folder that is always removed. A source that cannot be read is 422; OKF problems are
`errors` in the preview (validate) or 422 (import); the engine lint's findings are `warnings` and do not block.
"""
import os
import re
import shutil
import tempfile

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from kb_distillery.server.models.kb_import import KbImportPreview, KbImportResult
from kb_distillery import import_kb as svc
from kb_distillery.import_kb import BundleError

router = APIRouter(tags=["kb"])

_BODY = {"requestBody": {"required": True, "content": {
    "multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {
        "file": {"type": "string", "format": "binary"}, "id": {"type": "string"}, "kit": {"type": "string"}}}},
    "application/json": {"schema": {"type": "object", "required": ["git_url"], "properties": {
        "git_url": {"type": "string"}, "id": {"type": ["string", "null"]}, "kit": {"type": ["string", "null"]}}}},
}}}


async def _with_source(request: Request, work):
    """Resolve the body to a source on disk, run `work(source, id, kit, label)` in a thread, always clean up."""
    ctype = request.headers.get("content-type", "")
    stage = tempfile.mkdtemp(prefix="kb-upload-")
    try:
        if ctype.startswith("multipart/form-data"):
            form = await request.form()
            up = form.get("file")
            if up is None or isinstance(up, str):
                raise HTTPException(422, "send the bundle as a .zip in the `file` field")
            name = os.path.basename(up.filename or "bundle.zip")
            stem = re.sub(r"[^A-Za-z0-9._-]+", "-", os.path.splitext(name)[0]).strip("-.") or "bundle"
            source = os.path.join(stage, stem + ".zip")
            with open(source, "wb") as out:
                shutil.copyfileobj(up.file, out)
            kb_id, kit, label = form.get("id") or None, form.get("kit") or None, name
            if not all(v is None or isinstance(v, str) for v in (kb_id, kit)):
                raise HTTPException(422, "`id` and `kit` are text fields")
        elif ctype.startswith("application/json"):
            try:
                body = await request.json()
                source, kb_id, kit = body["git_url"], body.get("id") or None, body.get("kit") or None
            except (ValueError, KeyError, TypeError):
                raise HTTPException(422, "send JSON {git_url, id?, kit?}") from None
            if not isinstance(source, str) or not all(v is None or isinstance(v, str) for v in (kb_id, kit)):
                raise HTTPException(422, "git_url, id and kit must be text")
            source = svc.check_git_url(source)
            label = None
        else:
            raise HTTPException(415, "send a multipart .zip upload or JSON {git_url}")
        return await run_in_threadpool(work, source, str(kb_id) if kb_id else None, str(kit) if kit else None, label)
    except BundleError as e:
        raise HTTPException(422, str(e)) from None
    finally:
        shutil.rmtree(stage, ignore_errors=True)


@router.post("/api/kb/import/validate", response_model=KbImportPreview, summary="Dry run of a knowledge base import",
             openapi_extra=_BODY)
async def validate_import(request: Request):
    return await _with_source(request, svc.preview)


@router.post("/api/kb/import", response_model=KbImportResult, summary="Import an OKF bundle as a new knowledge base",
             openapi_extra=_BODY)
async def import_new_kb(request: Request):
    return await _with_source(request, svc.import_new)
