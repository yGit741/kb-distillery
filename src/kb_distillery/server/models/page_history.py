"""Page history (mirrors kb_distillery.proposals.history)."""
from pydantic import Field

from kb_distillery.server.models.base import ApiModel
from kb_distillery.server.models.proposals import Hunk, RenderPage


class PageVersion(ApiModel):
    sha: str
    short: str
    date: str
    subject: str
    kind: str                       # the op of a `kb(<op>): …` commit, else "other"


class PageHistory(ApiModel):
    slug: str
    versions: list[PageVersion]


class PageCompare(ApiModel):
    from_: str = Field(alias="from")
    to: str
    hunks: list[Hunk]
    page: RenderPage                # the `from` text as blocks, for the diff components' unchanged paragraphs


class RestoreRequest(ApiModel):
    sha: str
    blocks: list[str] | None = None  # compare hunk ids; absent = the whole version
    to: str = "working"              # the side the block ids were computed against


class RestoreResult(ApiModel):
    proposal_id: str
