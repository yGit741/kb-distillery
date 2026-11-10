"""Ingest from the app (mirrors kb_distillery.services.ingest_ui)."""
from kb_distillery.server.models.base import ApiModel


class IngestUrlRequest(ApiModel):
    """The JSON form of POST /api/ingest; the multipart form carries `file` plus the same three fields."""
    url: str
    tier: str = "full"                  # listed | easy | full | deep
    collection: str = ""                # a collection page slug, optional
    backend: str | None = None          # subscription | api | batch; None = the server default


class IngestStarted(ApiModel):
    job_id: str


class IngestStep(ApiModel):
    name: str                           # fetch | convert | digest | propose
    state: str                          # pending | active | done | skipped | failed
    detail: str = ""


class IngestJob(ApiModel):
    id: str
    status: str                         # running | done | failed
    source: str
    tier: str
    collection: str = ""
    steps: list[IngestStep]
    proposal_id: str | None = None      # set when status is done
    pages: list[str] = []               # the pages the proposal creates or edits
    error: str | None = None            # set when status is failed, in plain words
