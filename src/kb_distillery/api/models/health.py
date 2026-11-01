"""GET /api/health — mirrors kb_distillery.services.health.build_health_snapshot() (kb_distillery.core.health.build_snapshot)."""
from typing import Any

from kb_distillery.api.models.base import ApiModel


class HealthValues(ApiModel):
    errors: int
    warnings: int
    hooks: str
    broken: int
    orphans: int
    queued: int
    coherence_internal: int
    coherence_external: int
    coherence_cosmetic: int
    coherence_open: int
    lint_ms: float
    sha1_ms: float
    wiki_ms: float
    links_ms: float
    raw_tokens: int
    wiki_tokens: int
    index_savings_pct: int
    queued_mb: float
    partial_books: int | None = None
    scopes: int | None = None
    scope_uncovered: int | None = None
    persons_unverified: int | None = None
    person_unknowns: int | None = None
    lineage_stubs: int | None = None
    to_read_stubs: int | None = None


class HealthSnapshot(ApiModel):
    generated_at: str
    values: HealthValues
    statuses: dict[str, str]                      # metric key -> "ok" | "warn" | "bad" ...
    hooks_ok: bool
    inbox_count: int
    wiki_pages: int
    raw_files: int
    orphan_slugs: list[str]
    compression_pct: int
    graphs: dict[str, dict[str, Any]]             # chart series keyed by chart name
    partial_books: list[dict[str, Any]] = []
    lineage_stubs: list[Any] = []
