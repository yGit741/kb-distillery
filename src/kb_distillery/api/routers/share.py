"""GET /api/share/status — {status, chip} of the last deploy."""
from fastapi import APIRouter

from kb_distillery.api.models.share import ShareStatus

router = APIRouter(tags=["share"])


def share_status():
    from kb_distillery.dashboard.shell import share_state    # the publisher decides; no publisher = a chip that says so
    return share_state()


@router.get("/api/share/status", response_model=ShareStatus, summary="Last deploy of the private site")
def get_share_status():
    return share_status()
