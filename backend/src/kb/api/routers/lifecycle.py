"""GET /api/lifecycle — versions, history, snapshots, branches, guardrails (read-only git)."""
from fastapi import APIRouter, Query

from kb.api.models.lifecycle import LifecycleSnapshot
from kb.paths import vault_root
from kb.services.lifecycle import build_lifecycle_snapshot

router = APIRouter(tags=["lifecycle"])


@router.get("/api/lifecycle", response_model=LifecycleSnapshot, summary="Git lifecycle snapshot")
def get_lifecycle(limit: int = Query(150, ge=1, le=1000)):
    snap = build_lifecycle_snapshot(vault_root(), limit=limit)
    # JSON object keys must be strings; an op-less commit counts under None
    stats = snap.get("stats") or {}
    if "ops_30d" in stats:
        stats["ops_30d"] = {str(k): v for k, v in stats["ops_30d"].items()}
    return snap
