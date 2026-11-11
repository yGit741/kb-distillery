"""Models of the sources behind one wiki page."""
from kb_distillery.server.models.base import ApiModel


class PageSource(ApiModel):
    id: str                                     # raw path, page slug or URL: unique within the page
    title: str
    kind: str = "other"                         # pdf | web | youtube | chat | email | slides | image | handwritten | page | other
    format: str = ""                            # raw folder (printed-docs, web-clips, ...) or "page"
    disposition: str = ""                       # corpus disposition, "page" for a wiki source page, "external" for a URL
    path_rel: str | None = None                 # raw/... path when a raw file backs it
    slug: str | None = None                     # the wiki page that digests it, when there is one
    url: str | None = None
    route: str | None = None                    # app route that opens it (raw viewer or page)
    via: list[str] = []                         # raw | sources | corpus | links: what named it (links: a link in the text)
    cited_in_sections: list[str] = []           # headings of the sections that mention it
    added: str | None = None


class PageSourceCounts(ApiModel):
    total: int = 0
    raw: int = 0
    pages: int = 0
    external: int = 0
    by_disposition: dict[str, int] = {}


class PageSources(ApiModel):
    slug: str
    sources: list[PageSource] = []
    counts: PageSourceCounts = PageSourceCounts()
