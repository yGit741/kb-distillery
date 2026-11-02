"""Models of GET /api/graph — the wiki link graph (nodes, links, facets; `layer=raw` adds the data layer)."""
from pydantic import Field

from kb_distillery.api.models.base import ApiModel


class GraphNode(ApiModel):
    id: str                              # the slug; `<kb>:<slug>` when several knowledge bases share the canvas
    kb: str | None = None                # the knowledge base the page is from
    slug: str | None = None
    label: str = ""
    title: str = ""
    type: str = ""
    layer: str = ""                      # source | collection | concept
    maturity: str = ""                   # the reading lifecycle (was `status`)
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


class GraphRelation(GraphLink):
    """A typed relation (flag `graph-relations`, kb_distillery.graph.relations), keyed (source, target, kind)."""
    kind: str                            # a stored kind from kb.toml [edges] types, or mentions | shares-source |
                                         # advisor-of | student-of | name-match | collaborates-with | similar-to
    origin: str                          # stored (the page's `relations:` block) | computed
    note: str = ""
    weight: float = 1.0


class ConceptLink(ApiModel):
    source: str
    target: str
    shared: int


class GraphFacets(ApiModel):
    types: list[str] = []
    maturities: list[str] = []
    areas: list[str] = []


class GraphKb(ApiModel):
    id: str
    name: str = ""
    active: bool = False                 # the server's own knowledge base (the only one that can be edited)


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
    kbs: list[GraphKb] | None = None     # the knowledge bases on the canvas
    relations: list[GraphRelation] | None = None   # typed relations; null while the graph-relations flag is off
