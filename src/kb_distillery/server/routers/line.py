"""POST /api/line/route — a plain line the browser's rules could not place, read by the shared LLM tool."""
from fastapi import APIRouter, Depends

from kb_distillery.server.models.line import LineRouteRequest, LineRouteResponse
from kb_distillery.server.readonly import refuse_when_read_only
from kb_distillery.services import line_route

router = APIRouter(tags=["graph"])


@router.post("/api/line/route", dependencies=[Depends(refuse_when_read_only)], response_model=LineRouteResponse, response_model_exclude_none=True,
             summary="Read a plain line as a page search, a view change, a command or a question")
def post_line_route(body: LineRouteRequest):
    return line_route.route(body.text, [c.model_dump() for c in body.commands], backend=body.backend,
                            fallback=body.fallback)
