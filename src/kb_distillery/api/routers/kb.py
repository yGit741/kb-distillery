"""GET /api/kb (the knowledge base this app serves), GET /api/kb/list (every one in the bases dir)."""
from fastapi import APIRouter

from kb_distillery.api.models.kb import KbInfo, KbList
from kb_distillery.services import kb as svc

router = APIRouter(tags=["kb"])


@router.get("/api/kb", response_model=KbInfo, summary="The active knowledge base: kb.toml, folder, git, types")
def get_kb():
    return svc.active()


@router.get("/api/kb/list", response_model=KbList, summary="Knowledge bases the explorer can load")
def list_kbs():
    return svc.listing()
