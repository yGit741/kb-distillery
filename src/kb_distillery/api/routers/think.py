"""Think notes: list / read / save think/*.md and quick capture (kb_distillery.services.think).

The writes are the user's own edits made in the app; kb_distillery.ops.core sweeps them into a kb(think)
commit (before each op and nightly), so no git happens here.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kb_distillery.api.models.think import (ThinkCaptureRequest, ThinkList, ThinkNote, ThinkSaveRequest,
                                 ThinkWriteResult)
from kb_distillery.services import think as think_data

router = APIRouter(tags=["think"])


def _error(e: think_data.ThinkError):
    return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/api/think", response_model=ThinkList, summary="Top-level think notes, newest first")
def list_notes():
    return think_data.list_notes()


@router.post("/api/think/capture", response_model=ThinkWriteResult, summary="Append a quick thought to the inbox note")
def capture(body: ThinkCaptureRequest):
    try:
        return think_data.capture(body.text)
    except think_data.ThinkError as e:
        return _error(e)


@router.get("/api/think/{name}", response_model=ThinkNote, summary="One think note")
def get_note(name: str):
    try:
        return think_data.get_note(name)
    except think_data.ThinkError as e:
        return _error(e)


@router.put("/api/think/{name}", response_model=ThinkWriteResult, summary="Save a think note (optimistic lock on base_mtime)")
def save_note(name: str, body: ThinkSaveRequest):
    try:
        return think_data.save_note(name, body.text, body.base_mtime, create=bool(body.create))
    except think_data.ThinkError as e:
        return _error(e)
