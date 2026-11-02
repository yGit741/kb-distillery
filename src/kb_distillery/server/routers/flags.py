"""GET /api/flags, PUT /api/flags/{name} — runtime overrides, owner-only (thin over kb_distillery.services.flags)."""
from fastapi import APIRouter, Header, HTTPException

from kb_distillery.server.models.flags import FlagOverride, FlagsSnapshot
from kb_distillery.services import flags as svc

router = APIRouter(tags=["flags"])


@router.get("/api/flags", response_model=FlagsSnapshot, summary="Flag registry + effective value per flag")
def get_flags():
    return svc.list_flags()


@router.put("/api/flags/{name}", response_model=FlagsSnapshot,
            summary="Set or clear a runtime flag override (owner token required)")
def put_flag(name: str, body: FlagOverride, x_kb_owner_token: str | None = Header(default=None)):
    try:
        return svc.set_override(name, body.value, x_kb_owner_token)
    except svc.FlagRefused as e:
        raise HTTPException(e.status, str(e)) from None
