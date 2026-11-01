"""GET /api/ops — the Ops snapshot (?refresh=1 reruns the checks). A failure is 500 {"error": …} like legacy."""
from fastapi import APIRouter
from starlette.responses import JSONResponse

from kb_distillery.api.models.ops import OpsSnapshot
from kb_distillery.services import ops

router = APIRouter(tags=["ops"])


@router.get("/api/ops", response_model=OpsSnapshot, summary="Ops snapshot")
def get_ops(refresh: str = ""):
    try:
        return ops.build_ops_snapshot(refresh=refresh == "1")
    except Exception as exc:  # noqa: BLE001 — the tab shows the error instead of a blank page
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)
