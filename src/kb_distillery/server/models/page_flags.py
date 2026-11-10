"""Flags on a page (mirrors kb_distillery.proposals.flags)."""
from typing import Literal

from kb_distillery.server.models.base import ApiModel
from kb_distillery.server.models.page_chat import Skipped


class PageFlag(ApiModel):
    id: str
    block_at: int | None = None
    text: str
    note: str = ""
    created: str = ""
    resolved_by: str | None = None
    orphaned: bool = False


class PageFlagList(ApiModel):
    slug: str
    flags: list[PageFlag] = []


class PageFlagRequest(ApiModel):
    text: str
    note: str = ""
    block_at: int | None = None


class PageFlagRemoved(ApiModel):
    id: str


class PageFlagCount(ApiModel):
    open: int = 0
    orphaned: int = 0


class PageFlagFixRequest(ApiModel):
    backend: Literal["subscription", "api", "batch"] | None = None


class PageFlagFixReply(ApiModel):
    reply: str = ""
    proposal_id: str | None = None
    hunks: int = 0
    flag_ids: list[str] = []
    orphaned: list[str] = []
    skipped: list[Skipped] = []
