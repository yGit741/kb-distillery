"""Raw corpus: per-format tables, one file's preview, bytes, thumbnail, and the easy-digest action."""
import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, JSONResponse, Response

from kb.api.models.corpus import CorpusTable, DigestResult, ErrorBody, RawPreview
from kb.api.security import safe_raw_path
from kb.services import corpus

router = APIRouter(tags=["corpus"])

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}
RAW_TYPES = {**IMAGE_TYPES, ".pdf": "application/pdf", ".md": "text/plain; charset=utf-8",
             ".txt": "text/plain; charset=utf-8", ".json": "text/plain; charset=utf-8",
             ".html": "text/plain; charset=utf-8", ".eml": "text/plain; charset=utf-8"}
THUMB_WIDTH = 360


def rel_of(full: str) -> str:
    return os.path.relpath(full, corpus.ROOT).replace(os.sep, "/")


@router.get("/api/corpus", response_model=CorpusTable, summary="Raw files of one format with digest columns",
            responses={400: {"model": ErrorBody}})
def get_corpus(format: str = Query("")):
    data = corpus.build_corpus(format)
    if data is None:
        return JSONResponse({"error": "unknown format", "formats": list(corpus.FORMATS)}, status_code=400)
    return data


# the suffixed routes come first: `{path:path}` would swallow `/thumb`, `/file` and `/digest`
@router.get("/api/raw/{path:path}/thumb", summary="Page-1 PNG of a raw PDF (images are served as they are)",
            response_class=Response, responses={200: {"content": {"image/png": {}}}, 415: {"description": "no thumbnail"}})
def get_raw_thumb(full: str = Depends(safe_raw_path), w: int = Query(THUMB_WIDTH)):
    ext = os.path.splitext(full)[1].lower()
    if ext in IMAGE_TYPES:
        return FileResponse(full, media_type=IMAGE_TYPES[ext])
    from kb.dashboard.serve import thumbnail_png     # lazy: the legacy module's imports are heavy
    png = thumbnail_png(full, w) if ext == ".pdf" else None
    if not png:
        return JSONResponse({"error": "no thumbnail for this file"}, status_code=415)
    return Response(png, media_type="image/png")


@router.get("/api/raw/{path:path}/file", summary="The raw file itself (read-only)", response_class=Response)
def get_raw_file(full: str = Depends(safe_raw_path)):
    ctype = RAW_TYPES.get(os.path.splitext(full)[1].lower())
    if not ctype:
        return JSONResponse({"error": "unsupported file type"}, status_code=415)
    return FileResponse(full, media_type=ctype)


@router.post("/api/raw/{path:path}/digest", response_model=DigestResult,
             summary="Run easy-digest on one raw file (the only runnable action)")
def post_raw_digest(full: str = Depends(safe_raw_path)):
    result, err = corpus.run_action("easy-digest", rel_of(full))
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return result


@router.get("/api/raw/{path:path}", response_model=RawPreview, summary="Manifest facts and a text excerpt")
def get_raw(full: str = Depends(safe_raw_path)):
    data, err = corpus.build_preview(rel_of(full))
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return data
