"""GET /api/citations: the citation graph among cataloged papers (mirrors kb.services.corpus.build_citations)."""
from kb.api.models.base import ApiModel


class CitationNode(ApiModel):
    id: str
    title: str
    year: int | None = None
    citationCount: int = 0


class CitationLink(ApiModel):
    source: str
    target: str


class CitationGraph(ApiModel):
    nodes: list[CitationNode]
    links: list[CitationLink]
    missing: bool | None = None          # true when no citations cache exists yet
