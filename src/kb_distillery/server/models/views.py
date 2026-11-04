"""Pinned graph views and recent shaping steps (mirrors kb_distillery.services.views).

`spec` is opaque to the server: the frontend owns its shape (cypher, style, filters, layout, camera).
"""
from typing import Any

from kb_distillery.server.models.base import ApiModel


class View(ApiModel):
    id: str
    name: str
    created: str
    spec: dict[str, Any] = {}


class ViewList(ApiModel):
    views: list[View]


class ViewPinRequest(ApiModel):
    name: str
    spec: dict[str, Any] = {}
    id: str | None = None


class ViewRenameRequest(ApiModel):
    name: str


class ViewStep(ApiModel):
    ok: bool
    sha: str | None = None
    version: str | None = None
    view: View | None = None


class RecentStep(ApiModel):
    at: str
    text: str
    spec: dict[str, Any] = {}


class RecentList(ApiModel):
    recent: list[RecentStep]


class RecentAppendRequest(ApiModel):
    text: str
    spec: dict[str, Any] = {}
