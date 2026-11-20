"""GET /api/kb (the knowledge base this app serves), GET /api/kb/list (every one in the bases dir), GET /api/kb/stats
(their graph sizes), PUT /api/kb/{id}/star."""
from fastapi import APIRouter, HTTPException

from kb_distillery.config import kb as kbconfig
from kb_distillery.server.models.kb import KbGraphSizes, KbInfo, KbList, KbStarPut
from kb_distillery.services import kb as svc

router = APIRouter(tags=["kb"])


@router.get("/api/kb", response_model=KbInfo, summary="The active knowledge base: kb.toml, folder, git, types")
def get_kb():
    return svc.active()


@router.get("/api/kb/list", response_model=KbList, summary="Knowledge bases the explorer can load")
def list_kbs():
    return svc.listing()


@router.get("/api/kb/stats", response_model=KbGraphSizes,
            summary="Graph size of every knowledge base: concepts, sources, concept-to-concept edges")
def kb_stats():
    return svc.graph_sizes()


@router.put("/api/kb/{kb_id}/star", response_model=KbList, responses={404: {}},
            summary="Star (or unstar) a knowledge base: starred ones lead the header menu")
def star_kb(kb_id: str, body: KbStarPut):
    if kb_id not in kbconfig.discover():
        raise HTTPException(404, f"no knowledge base {kb_id!r} in {kbconfig.bases_dir()}")
    svc.set_star(kb_id, body.starred)
    return svc.listing()
