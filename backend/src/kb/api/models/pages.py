"""Models of the page explorer: index, one page, full-text search, shortest paths, vault assets."""
from kb.api.models.base import ApiModel


class PageCard(ApiModel):
    id: str
    title: str = ""
    type: str = "unknown"
    status: str = ""
    depth: str = ""                      # listed | easy | full | deep
    areas: list[str] = []
    year: int | None = None
    # `in` / `out` (link counts) pass through as extra keys: `in` is a Python keyword
    words: int = 0
    mtime: float | int | str | None = None
    preview: str = ""


class WantedLink(ApiModel):
    id: str
    count: int
    # `from` is a keyword: it passes through as an extra key


class PageIndex(ApiModel):
    generated_at: str
    pages: list[PageCard]
    links: list[list[str]]
    wanted: list[WantedLink] = []
    wanted_total: int = 0


class Backlink(ApiModel):
    id: str
    context: str = ""


class SuggestedPage(ApiModel):
    id: str
    score: float
    via: list[str] = []
    shared: int = 0


class PageDetail(ApiModel):
    card: PageCard
    path: str
    frontmatter: dict
    markdown: str
    backlinks: list[Backlink] = []
    outbound: list[str] = []
    broken: list[str] = []
    suggested: list[SuggestedPage] = []


class SearchHit(ApiModel):
    id: str
    title: str = ""
    type: str = "unknown"
    depth: str | None = None             # set on related hits and in the search ports; legacy hits may omit it
    snippet: str = ""
    score: int = 0


class SearchResult(ApiModel):
    query: str | None = None
    total: int
    hits: list[SearchHit]
    related: list[SearchHit] | None = None   # meaning-based hits (qmd over summaries), flag semantic-search


class PathHop(ApiModel):
    dir: str                             # forward | back
    context: str = ""
    # `from` / `to` pass through as extra keys (legacy names)


class PathRoute(ApiModel):
    nodes: list[str]
    hops: list[PathHop]


class PathResult(ApiModel):
    a: str
    b: str
    distance: int | None = None          # null when the pages are not connected
    paths: list[PathRoute] = []
