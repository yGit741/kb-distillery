"""A scrap-youtube video bundle: transcript sections, frames and their reads, description, comments."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kb.api.models.videos import VideoBundle
from kb.services import videos as svc

router = APIRouter(tags=["videos"])


@router.get("/api/videos/{path:path}", response_model=VideoBundle,
            summary="One video bundle (raw/videos/<dir>/video.md) as structured data",
            responses={404: {"description": "not a video bundle"}})
def get_video(path: str):
    data = svc.load_bundle(path if path.startswith("raw/") else f"raw/{path}")
    if data is None:
        return JSONResponse({"error": "not a video bundle"}, status_code=404)
    return data
