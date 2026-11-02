"""GET /api/share/status — {status, chip} of the last deploy."""
from fastapi import APIRouter
from starlette.responses import PlainTextResponse

from kb_distillery.api.models.share import ShareStatus

router = APIRouter(tags=["share"])


def share_status():
    from kb_distillery.publish.site_state import share_state    # the publisher decides; no publisher = a chip that says so
    return share_state()


@router.get("/api/share/status", response_model=ShareStatus, summary="Last deploy of the private site")
def get_share_status():
    return share_status()


@router.get("/share-log", response_class=PlainTextResponse, include_in_schema=False)
def get_share_log():
    """The tail of the publisher's log: where the share chip links for a deploy that is not live."""
    from kb_distillery.publish.site_state import share_log_tail
    return PlainTextResponse(share_log_tail(), media_type="text/plain; charset=utf-8")
