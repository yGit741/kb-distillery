"""GET /api/static/{name} — the dashboard's own css/js (what the legacy /static/ serves), nothing else."""
import os

from fastapi import APIRouter, HTTPException
from starlette.responses import FileResponse

from kb.dashboard.serve import STATIC_DIR

router = APIRouter(tags=["assets"])


@router.get("/api/static/{name:path}", summary="A dashboard static file (css/js)",
            responses={404: {"description": "no such file"}})
def get_static(name: str):
    root = os.path.realpath(STATIC_DIR)
    full = os.path.realpath(os.path.join(root, os.path.normpath(name)))
    if not full.startswith(root + os.sep) or not os.path.isfile(full) or ".." in name.split("/"):
        raise HTTPException(404, "no such file")
    return FileResponse(full, media_type="text/css" if full.endswith(".css") else "application/javascript",
                        headers={"Cache-Control": "no-cache"})
