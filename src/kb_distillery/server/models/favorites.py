"""Favorite pages (mirrors kb_distillery.services.favorites)."""
from kb_distillery.server.models.base import ApiModel


class FavoriteList(ApiModel):
    slugs: list[str]


class FavoriteAddRequest(ApiModel):
    slug: str


class FavoriteStep(ApiModel):
    ok: bool
    sha: str | None = None
    version: str | None = None
    slugs: list[str] = []
    reason: str | None = None
