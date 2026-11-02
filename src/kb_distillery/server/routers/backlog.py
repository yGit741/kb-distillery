"""GET /api/backlog — the local backlog cards (thin over kb_distillery.services.backlog). Read-only; local app only."""
from fastapi import APIRouter

from kb_distillery.server.models.backlog import BacklogList
from kb_distillery.services import backlog as svc

router = APIRouter(tags=["backlog"])


@router.get("/api/backlog", response_model=BacklogList, summary="Backlog items with plan status and drift")
def list_backlog():
    return svc.list_items()
