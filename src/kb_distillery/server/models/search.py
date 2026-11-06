"""Full-text search over pages, think notes, chats and raw text (mirrors kb_distillery.search.fts)."""
from typing import Literal

from kb_distillery.server.models.base import ApiModel


class TextHit(ApiModel):
    kind: Literal["page", "think", "chat", "raw"]
    id: str                 # page slug, think note name, chat session id, or the raw file's repo path
    title: str
    snippet: str = ""
    score: float = 0.0
    path: str = ""


class TextSearch(ApiModel):
    query: str
    hits: list[TextHit]
