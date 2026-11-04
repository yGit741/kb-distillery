"""Chat attachments (agent-mode flag): upload, list and delete the files of one chat session.

Stored under `.cache/chat/<session>/attachments/` (never raw/ or wiki/). Errors keep the chat shape {"error": …}.
"""
from fastapi import APIRouter, File, Form, UploadFile
from starlette.responses import JSONResponse

from kb_distillery.config.flags import runtime
from kb_distillery.server.models.chat import AttachmentInfo, AttachmentList
from kb_distillery.services import chat_attachments as svc

router = APIRouter(tags=["chat"])


def _err(code, message):
    return JSONResponse({"error": message}, status_code=code)


def _off():
    return None if runtime.effective("agent-mode") else _err(404, "attachments are disabled")


@router.post("/api/chat/attachments", response_model=AttachmentInfo, summary="Upload a chat attachment",
             responses={400: {}, 404: {}, 409: {}, 413: {}, 415: {}})
def post_attachment(session: str = Form(...), file: UploadFile = File(...)):
    if (off := _off()):
        return off
    try:
        return svc.add(session, file.filename, file.file)
    except svc.AttachmentError as exc:
        return _err(exc.status, exc.message)


@router.get("/api/chat/attachments/{session}", response_model=AttachmentList, summary="List a chat's attachments",
            responses={400: {}, 404: {}})
def get_attachments(session: str):
    if (off := _off()):
        return off
    try:
        return {"attachments": [svc.public(e) for e in svc.listing(session)]}
    except svc.AttachmentError as exc:
        return _err(exc.status, exc.message)


@router.delete("/api/chat/attachments/{session}/{attachment_id}", response_model=AttachmentList,
               summary="Remove a chat attachment", responses={400: {}, 404: {}})
def delete_attachment(session: str, attachment_id: str):
    if (off := _off()):
        return off
    try:
        svc.remove(session, attachment_id)
        return {"attachments": [svc.public(e) for e in svc.listing(session)]}
    except svc.AttachmentError as exc:
        return _err(exc.status, exc.message)
