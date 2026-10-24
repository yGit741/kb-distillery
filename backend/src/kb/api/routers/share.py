"""GET /api/share/status — {status, chip} of the last deploy."""
from fastapi import APIRouter

from kb.api.models.share import ShareStatus

router = APIRouter(tags=["share"])


def share_status():
    try:
        from kb.share.contracts import StatusFile
        status = StatusFile().read()
    except Exception:  # noqa: BLE001 — must render without the share package
        status = None
    from kb.dashboard.shell import share_chip
    return {"status": status, "chip": share_chip(status)}


@router.get("/api/share/status", response_model=ShareStatus, summary="Last deploy of the private site")
def get_share_status():
    return share_status()
