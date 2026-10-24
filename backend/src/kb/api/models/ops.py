"""GET /api/ops — the Ops tab snapshot (nightly report model, runs, hygiene, threads)."""
from typing import Any

from kb.api.models.base import ApiModel


class OpsSnapshot(ApiModel):
    subject: str | None = None
    doc: dict[str, Any] = {}
