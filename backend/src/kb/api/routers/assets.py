"""GET /api/assets/{name} — an image embedded in a page (Obsidian embed name), served from raw/ only."""
import os

from fastapi import APIRouter, HTTPException
from starlette.responses import FileResponse

from kb.services import pages

router = APIRouter(tags=["assets"])

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}


@router.get("/api/assets/{name:path}", summary="An image asset under raw/",
            responses={200: {"content": {"image/*": {}}}, 404: {"description": "no such asset"}})
def get_asset(name: str):
    full = pages.resolve_asset(name)       # image extensions only; confined to raw/ (no traversal)
    if not full:
        raise HTTPException(404, "no such asset")
    return FileResponse(full, media_type=IMAGE_TYPES.get(os.path.splitext(full)[1].lower(),
                                                        "application/octet-stream"))
