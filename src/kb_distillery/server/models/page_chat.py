"""Chat on a page (mirrors kb_distillery.proposals.chat)."""
from typing import Literal

from kb_distillery.server.models.base import ApiModel


class Selection(ApiModel):
    block_at: int | None = None
    text: str = ""


class PageChatRequest(ApiModel):
    message: str
    selections: list[Selection] = []
    mentions: list[str] = []
    backend: Literal["subscription", "api", "batch"] | None = None


class Skipped(ApiModel):
    before: str
    reason: str


class PageChatReply(ApiModel):
    reply: str
    proposal_id: str | None = None
    hunks: int = 0
    skipped: list[Skipped] = []
    unknown_mentions: list[str] = []


class ChatMessage(ApiModel):
    role: Literal["user", "assistant"]
    text: str
    at: str = ""
    selections: list[Selection] = []
    mentions: list[str] = []
    proposal_id: str | None = None
    hunks: int = 0
    skipped: list[Skipped] = []
    unknown_mentions: list[str] = []


class PageChatThread(ApiModel):
    slug: str
    messages: list[ChatMessage] = []


class MentionHit(ApiModel):
    slug: str
    title: str


class MentionList(ApiModel):
    pages: list[MentionHit] = []
