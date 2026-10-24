"""GET /api/pipeline — the ingestion/digestion snapshot (the old /api/digestion)."""
from typing import Any

from kb.api.models.base import ApiModel


class PipelineSnapshot(ApiModel):
    """Superset of the legacy JSON; the keys the pipeline screen reads are listed, the rest pass through."""
    generated_at: str | None = None
    items: list[dict[str, Any]] = []
    inbox: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []
    coherence: list[dict[str, Any]] = []
    counts: dict[str, Any] = {}
