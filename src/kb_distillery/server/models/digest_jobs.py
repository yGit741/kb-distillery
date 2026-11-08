"""Digest jobs from the app (mirrors kb_distillery.services.digest_jobs)."""
from kb_distillery.server.models.base import ApiModel


class DigestRequest(ApiModel):
    """Raw paths to digest in full. `backend` (subscription | api | batch) and `model` are optional: left out, the billing
    defaults pick them (`backend_why` in the reply says which rule did)."""
    raws: list[str]
    backend: str | None = None
    model: str | None = None


class SkippedSource(ApiModel):
    raw: str
    reason: str


class Estimate(ApiModel):
    tokens_in: int
    tokens_out: int
    cost_usd: float                 # API price of the estimate (`llm.cost`; batch at half price)
    cost_worst_usd: float           # if every reply hit the token ceiling
    billed_usd: float               # what is billed per token: 0 on the subscription
    seconds: int                    # rough wall time
    eta: str


class BackendOption(Estimate):
    backend: str                    # subscription | api | batch
    available: bool
    why: str


class DigestPreview(Estimate):
    tier: str
    depth: str                      # full
    provider: str
    model: str
    backend: str
    backend_why: str
    sources: int
    requests: int                   # sources that can be filled (a book is digested by part, not here)
    skipped: list[SkippedSource]
    options: list[BackendOption]    # the same estimate on each of the three backends


class JobSource(ApiModel):
    raw: str
    status: str                     # pending | filling | digesting | finalized | failed | skipped | cancelled
    note: str = ""
    page: str | None = None         # wiki/<slug>.md once finalized
    seconds: float | None = None


class DigestJob(ApiModel):
    id: str
    status: str                     # queued | running | done | failed | cancelled
    created: str
    started: str | None = None
    finished: str | None = None
    backend: str
    backend_why: str = ""
    model: str
    provider: str
    tier: str
    depth: str
    current: str | None = None      # the raw path being digested now
    spent_usd: float = 0.0
    error: str | None = None
    sources: list[JobSource]


class DigestJobList(ApiModel):
    jobs: list[DigestJob]
