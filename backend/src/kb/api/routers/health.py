"""GET /api/health — the vault health snapshot (reference router: thin over a service, typed)."""
from fastapi import APIRouter

from kb.api.models.health import HealthSnapshot
from kb.services.health import build_health_snapshot

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthSnapshot, summary="Vault health snapshot")
def get_health():
    return build_health_snapshot()
