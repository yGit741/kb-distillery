"""Scopes: personal working sets of raw files (mirrors kb_distillery.services.scopes)."""
from kb_distillery.api.models.base import ApiModel


class ScopeSummary(ApiModel):
    slug: str
    title: str
    status: str
    files: int
    digested: int
    uncovered: int
    coverage: float | None = None
    updated: str | None = None


class ScopeList(ApiModel):
    scopes: list[ScopeSummary]


class ScopeRow(ApiModel):
    path: str
    format: str = ""
    disposition: str | None = None
    slug: str | None = None
    page_type: str | None = None
    digestion: str = ""
    collection: list[str] = []
    year: int | None = None


class ScopeProjection(ApiModel):
    hop0: list = []
    hop1: list = []
    covered: list = []
    uncovered: list = []
    coverage: float | None = None
    hubs: list = []
    themes: list = []


class ScopeDetail(ApiModel):
    slug: str
    title: str
    why: str = ""
    status: str
    rows: list[ScopeRow]
    projection: ScopeProjection


class ScopeResolveRequest(ApiModel):
    nodes: list[str]


class ScopeResolved(ApiModel):
    paths: list[str]
    rows: list[ScopeRow]


class ScopeSaveRequest(ApiModel):
    slug: str
    why: str = ""
    title: str = ""
    paths: list[str] = []
    create: bool = False


class ScopeDuplicateRequest(ApiModel):
    new_slug: str
    title: str = ""


class ScopeStep(ApiModel):
    """One kb(refine) step: the commit sha and the knowledge version it produced."""
    ok: bool
    sha: str | None = None
    slug: str
    version: str | None = None
