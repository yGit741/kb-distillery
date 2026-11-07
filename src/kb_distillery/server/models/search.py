"""Models of meaning search: pages close in meaning to a phrase or a page."""
from kb_distillery.server.models.base import ApiModel


class SimilarHit(ApiModel):
    slug: str
    title: str = ""
    score: int = 0                       # 0 to 100, higher is closer


class SimilarResult(ApiModel):
    hits: list[SimilarHit]
