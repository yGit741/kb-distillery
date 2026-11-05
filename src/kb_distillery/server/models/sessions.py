from typing import Any, Literal

from pydantic import Field

from kb_distillery.server.models.base import ApiModel


class SessionUsage(ApiModel):
    cost_usd: float = 0
    turns: int = 0


class SessionSummary(ApiModel):
    id: str
    title: str
    created: str
    updated: str
    turns: int = 0
    cost_usd: float = 0
    preview: str = ""                          # the first line of the first question
    model: str | None = None
    effort: str | None = None
    backend: str | None = None
    status: Literal["running", "waiting", "error", "idle"] = "idle"   # from the last message (sessions_store.status_of)


class SessionList(ApiModel):
    sessions: list[SessionSummary]             # newest first


class SessionDoc(ApiModel):
    id: str
    title: str
    created: str
    updated: str
    model: str | None = None
    effort: str | None = None
    backend: str | None = None
    messages: list[dict[str, Any]]             # as the frontend keeps them; the server never interprets them
    usage: SessionUsage


class SessionPutRequest(ApiModel):
    messages: list[dict[str, Any]] = Field(description="the whole conversation")
    title: str | None = Field(None, description="omit to keep the stored title (a new session takes its first question)")
    created: str | None = Field(None, description="ISO-8601 time of a new session (a migrated chat keeps its own); ignored when the session exists")
    model: str | None = None
    effort: str | None = None
    backend: str | None = None


class SessionRenameRequest(ApiModel):
    title: str


class SessionDeleted(ApiModel):
    ok: bool
    id: str
