"""POST /api/inbox/files and POST /api/inbox/link-folder: add sources to the kb from the app, with no model call.

Files land in raw/inbox/ and are catalogued as `distill ingest` does; each call is one `kb(catalog)` knowledge step. A read-only
server (KB_READ_ONLY=1) answers both with 405, like every other write. The upload gets the 64 MB body cap (`security.UPLOAD_PATHS`).
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from kb_distillery.server.models.inbox_add import InboxAddResult, LinkFolderRequest, LinkFolderResult
from kb_distillery.server.readonly import refuse_when_read_only
from kb_distillery.services import inbox_add as svc

router = APIRouter(tags=["inbox"])
ERRORS = {405: {}, 409: {}, 413: {}, 422: {}}


@router.post("/api/inbox/files", dependencies=[Depends(refuse_when_read_only)], response_model=InboxAddResult, responses=ERRORS,
             summary="Add uploaded files to the knowledge base (no model call, one knowledge step)")
def add_files(files: list[UploadFile] = File(...)):
    try:
        return svc.add_files([(f.filename or "", f.file.read()) for f in files])
    except svc.SourceError as e:
        raise HTTPException(e.status, e.message) from None


@router.post("/api/inbox/link-folder", dependencies=[Depends(refuse_when_read_only)], response_model=LinkFolderResult, responses=ERRORS,
             summary="Take the supported files of a folder on this machine (no model call, one knowledge step)")
def link_folder(body: LinkFolderRequest):
    try:
        return svc.link_folder(body.path)
    except svc.SourceError as e:
        raise HTTPException(e.status, e.message) from None
