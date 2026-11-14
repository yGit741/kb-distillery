"""Models of GET /api/health/knowledge — anomaly groups over the wiki graph (computed per request, never stored)."""
from kb_distillery.server.models.base import ApiModel


class HealthPage(ApiModel):
    id: str
    title: str = ""
    layer: str = ""                      # source | collection | concept
    type: str = ""
    degree: int = 0                      # distinct linked pages, either direction
    depth: str | None = None             # undigested_sources only
    source: str | None = None            # single_source_concepts only: the one linked source id


class HealthPair(ApiModel):
    a: str
    a_title: str = ""
    b: str
    b_title: str = ""


class MissingLink(HealthPair):
    score: float                         # Jaccard over the two concepts' linked source pages
    shared: list[str]                    # shared source ids


class PageGroup(ApiModel):
    count: int                           # the full count; `items` is capped by `limit`
    items: list[HealthPage]


class MissingLinkGroup(ApiModel):
    count: int
    items: list[MissingLink]


class PairGroup(ApiModel):
    count: int
    items: list[HealthPair]


class KnowledgeHealth(ApiModel):
    undigested_sources: PageGroup
    orphans: PageGroup
    single_source_concepts: PageGroup
    missing_links: MissingLinkGroup
    unsupported_links: PairGroup
    hubs: PageGroup
