"""GET /api/share/status — the last deploy of the private site and the nav chip that shows it."""
from typing import Optional

from kb_distillery.server.models.base import ApiModel


class ShareDeploy(ApiModel):
    state: Optional[str] = None
    sha: Optional[str] = None
    kb_version: Optional[str] = None
    at: Optional[str] = None
    error: Optional[str] = None
    url: Optional[str] = None


class ShareChip(ApiModel):
    label: str
    cls: str
    title: str = ""
    href: str = ""


class ShareStatus(ApiModel):
    status: Optional[ShareDeploy] = None
    chip: Optional[ShareChip] = None
