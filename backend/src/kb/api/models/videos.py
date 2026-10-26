"""GET /api/videos/{path} — a scrap-youtube bundle (kb.services.videos.load_bundle)."""
from typing import Any

from kb.api.models.base import ApiModel


class VideoChapter(ApiModel):
    title: str
    start: float
    end: float | None = None


class VideoComment(ApiModel):
    author: str
    likes: int
    text: str
    stamps: list[str] = []


class VideoAnchor(ApiModel):
    """A timestamp the screen likely shows something worth reading; a digest tier reads the top ones."""
    t: float
    thumb: str
    path: str
    kind: str
    score: int
    why: list[str] = []
    ocr: list[str] = []


class VideoSection(ApiModel):
    chapter: str
    start: float
    end: float
    text: str


class VideoBundle(ApiModel):
    id: str
    title: str
    url: str
    raw: str
    channel: str | None = None
    duration: int
    uploaded: str | None = None
    description: str = ""
    links: list[str] = []
    chapters: list[VideoChapter] = []
    comments: list[VideoComment] = []
    comment_count: int | None = None
    subs_kind: str | None = None
    sections: list[VideoSection] = []
    anchors: list[VideoAnchor] = []
    stats: dict[str, Any] = {}
