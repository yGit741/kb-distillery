"""Models of GET /api/graph — the wiki link graph (nodes, links, facets; `layer=raw` adds the data layer)."""
from pydantic import Field

from kb.api.models.base import ApiModel


class GraphNode(ApiModel):
    id: str
    label: str = ""
    title: str = ""
    type: str = ""
    layer: str = ""                      # source | collection | concept
    status: str = ""
    depth: str = ""                      # listed | easy | full | deep (sources)
    areas: list[str] = []
    year: int | None = None
    inDegree: int = 0
    outDegree: int = 0
    path: str = ""
    added: str = ""                      # YYYY-MM-DD: first commit that touched the page ("" without git history)
    changed: str = ""                    # YYYY-MM-DD: last commit that touched it
    preview: str = ""
    properties: dict[str, str] = {}


class GraphLink(ApiModel):
    source: str
    target: str
    kind: str = "wikilink"               # wikilink | related | book


class ConceptLink(ApiModel):
    source: str
    target: str
    shared: int


class GraphFacets(ApiModel):
    types: list[str] = []
    statuses: list[str] = []
    areas: list[str] = []


class GraphSnapshot(ApiModel):
    generated_at: str
    etag: str
    node_count: int
    link_count: int
    nodes: list[GraphNode]
    links: list[GraphLink]
    schema_: dict = Field(default_factory=dict, alias="schema")
    concept_links: list[ConceptLink] = []
    facets: GraphFacets = GraphFacets()
    layer: str | None = None             # "raw" when the data layer is merged in
