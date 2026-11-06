"""Pages close in meaning to a phrase or to another page (0 LLM): the qmd service over the title+summary cards."""
from kb_distillery.search import qmd_client
from kb_distillery.search.semfind import load_pages
from kb_distillery.graph.snapshot import _title
from kb_distillery.vault import frontmatter
from kb_distillery.vault.summary import unquote

FLAG = "semantic-search"
K_MAX = 50


class SimilarError(Exception):
    """`status` is the HTTP status the router answers with; `detail` the reason shown to the person."""

    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _flag_on():
    from kb_distillery.config.flags import runtime
    from kb_distillery.services import flags
    return runtime.effective(FLAG, overrides_path=flags.OVERRIDES_PATH)


def _query_of(slug, pages):
    """A page's own card (title and summary) as the query."""
    _rel, fm, text = pages[slug]
    title = frontmatter.page_title(fm, text, slug)
    summary = unquote(fm.get("description"))
    return f"{title}\n\n{summary}" if summary else title


def similar(q="", slug="", k=20):
    """[{slug, title, score}] best first, never the `slug` page itself.

    Raises SimilarError: 422 with neither `q` nor `slug`, 404 for an unknown `slug`, 503 when semantic search is off
    or the qmd service is down."""
    q, slug = (q or "").strip(), (slug or "").strip()
    k = max(1, min(int(k), K_MAX))
    if not q and not slug:
        raise SimilarError(422, "give q (a phrase) or slug (a page)")
    if not _flag_on():
        raise SimilarError(503, "semantic search is off")
    pages = load_pages()
    if slug:
        if slug not in pages:
            raise SimilarError(404, "unknown slug")
        q = _query_of(slug, pages)
    found = qmd_client.search(q, limit=k + 1)
    if found is None:
        raise SimilarError(503, "the semantic search service is not running")
    by_key = {qmd_client.qmd_key(s): s for s in pages}
    out = []
    for key, score in found:
        s = by_key.get(key)
        if not s or s == slug:
            continue
        out.append({"slug": s, "title": _title(pages[s][2], s), "score": round(score * 100)})
        if len(out) >= k:
            break
    return out
