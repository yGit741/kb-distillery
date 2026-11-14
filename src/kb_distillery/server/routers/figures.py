"""Figures of a transcribed PDF (`![Figure 3.1](figure:<sha12>/p0073/1)` on wiki pages): the PNG cut from the page.
Read-only; dark behind the `parsed-pdf` flag like the transcript itself (no page links one while it is off)."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from kb_distillery.services import marks as svc

router = APIRouter(tags=["figures"])


@router.get("/api/figures/{sha12}/{page}/{fig_id}", responses={404: {}, 200: {"content": {"image/png": {}}}},
            summary="One figure of a transcribed PDF page (PNG)")
def get_figure(sha12: str, page: str, fig_id: int):
    try:
        path = svc.figure_file(sha12, page, fig_id)
    except svc.MarkError as e:
        raise HTTPException(e.status, e.message) from None
    return FileResponse(path, media_type="image/png")
