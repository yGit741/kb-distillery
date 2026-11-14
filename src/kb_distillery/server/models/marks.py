"""Unsure-formula marks (mirrors kb_distillery.services.marks)."""
from typing import Any, Literal

from kb_distillery.server.models.base import ApiModel


class MarkResolution(ApiModel):
    action: str                     # correct | fixed
    text: str = ""                  # the replacement when fixed
    slug: str = ""
    time: str = ""


class MarkDetail(ApiModel):
    """One mark record from the parsed store: `level` `!` (one voice decided) or `!!` (unsettled), `reason`, `text` (the
    formula now), `was` (what a fix replaced), `other` (the parser's reading). `crop_url` is null without a crop file."""
    id: Any
    level: str
    reason: str = ""
    text: str = ""
    was: str | None = None
    other: str | None = None
    page: str
    sha: str
    crop_url: str | None = None
    resolution: MarkResolution | None = None
    read_only: bool = False
    default_backend: str = "subscription"   # $KB_LLM_BACKEND, else subscription


class MarkResolveRequest(ApiModel):
    slug: str
    expected_current: str | None = None   # the formula as shown; 409 when the page now holds another


class MarkFixRequest(ApiModel):
    slug: str
    instruction: str
    backend: Literal["subscription", "api", "batch"] | None = None


class MarkFixReply(ApiModel):
    replacement: str                # the proposed formula, same form as the current one; not saved
    current: str = ""
    backend: str = ""


class MarkApplyRequest(ApiModel):
    slug: str
    replacement: str
    expected_current: str | None = None   # `current` from fix; 409 when the page changed since


class MarkStepResult(ApiModel):
    ok: bool
    slug: str
    commit: str | None = None       # the kb(refine) commit
    version: str | None = None
    warning: str | None = None      # the page changed but the decision was not recorded
