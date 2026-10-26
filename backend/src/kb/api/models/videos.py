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


class VideoRead(ApiModel):
    text: str = ""
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None


class VideoFrame(ApiModel):
    t: float
    file: str
    path: str
    kind: str
    ocr: list[str] = []
    conf: float | None = None
    read: VideoRead | None = None


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
    tier: str
    sections: list[VideoSection] = []
    frames: list[VideoFrame] = []
    stats: dict[str, Any] = {}
