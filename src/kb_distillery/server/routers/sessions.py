"""Chat sessions kept on this machine in `<kb>/.local/sessions/` (thin over kb_distillery.services.sessions_store).

The browser mirrors each finished turn with PUT; the list and one document are plain GETs. Never committed. A server
started with KB_READ_ONLY=1 refuses every write with 405 (reads still work); errors are `{"error": "..."}`.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kb_distillery.server.models.sessions import (SessionDeleted, SessionDoc, SessionList, SessionPutRequest,
                                                  SessionRenameRequest)
from kb_distillery.services import sessions_store as svc

router = APIRouter(tags=["sessions"])


def _error(e: svc.SessionsError):
    return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/api/sessions", response_model=SessionList, summary="Saved chat sessions, newest first")
def list_sessions():
    return svc.list_sessions()


@router.get("/api/sessions/{session_id}", response_model=SessionDoc, summary="One saved chat session")
def get_session(session_id: str):
    try:
        return svc.get_session(session_id)
    except svc.SessionsError as e:
        return _error(e)


@router.put("/api/sessions/{session_id}", response_model=SessionDoc, summary="Create or replace a chat session")
def put_session(session_id: str, body: SessionPutRequest):
    try:
        return svc.put_session(session_id, body.messages, title=body.title, created=body.created, model=body.model,
                               effort=body.effort, backend=body.backend)
    except svc.SessionsError as e:
        return _error(e)


@router.patch("/api/sessions/{session_id}", response_model=SessionDoc, summary="Rename a chat session")
def rename_session(session_id: str, body: SessionRenameRequest):
    try:
        return svc.rename_session(session_id, body.title)
    except svc.SessionsError as e:
        return _error(e)


@router.delete("/api/sessions/{session_id}", response_model=SessionDeleted, summary="Delete a chat session")
def delete_session(session_id: str):
    try:
        return svc.delete_session(session_id)
    except svc.SessionsError as e:
        return _error(e)
