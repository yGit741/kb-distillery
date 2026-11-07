"""Models of search: pages close in meaning to a phrase or a page, and full text over pages, think notes, chats and raw text."""
from typing import Literal

from kb_distillery.server.models.base import ApiModel


class SimilarHit(ApiModel):
    slug: str
    title: str = ""
    score: int = 0                       # 0 to 100, higher is closer


class SimilarResult(ApiModel):
    hits: list[SimilarHit]



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
