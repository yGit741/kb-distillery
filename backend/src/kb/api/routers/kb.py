"""GET /api/kb (the knowledge base this app serves), GET /api/kb/list (every one the explorer can see),
POST /api/kb/register (save a folder from anywhere on disk in the machine-local registry)."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kb import kbconfig
from kb.api.models.kb import KbInfo, KbList, KbRegister
from kb.services import kb as svc

router = APIRouter(tags=["kb"])


@router.get("/api/kb", response_model=KbInfo, summary="The active knowledge base: kb.toml, folder, git, types")
def get_kb():
    return svc.active()


@router.get("/api/kb/list", response_model=KbList, summary="Knowledge bases the explorer can load")
def list_kbs():
    return svc.listing()


@router.post("/api/kb/register", response_model=KbList, summary="Save a knowledge base folder from anywhere on disk",
             responses={400: {"description": "not a knowledge base this explorer can open"}})
def register_kb(body: KbRegister):
    try:
        return svc.register(body.path)
    except kbconfig.KbConfigError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
