"""Adding sources from the app (mirrors kb_distillery.services.inbox_add)."""
from kb_distillery.server.models.base import ApiModel


class InboxFileResult(ApiModel):
    """What happened to one uploaded file: `added` (stored and catalogued), `duplicate` (same content already in the kb),
    or `refused` (`reason` says why). `raw_path` is where an added file lives now."""
    name: str
    status: str                     # added | duplicate | refused
    reason: str | None = None
    raw_path: str | None = None


class InboxAddResult(ApiModel):
    files: list[InboxFileResult]
    commit: str | None = None       # the knowledge commit; None when nothing was added
    version: str | None = None


class LinkFolderRequest(ApiModel):
    path: str                       # an absolute folder on this machine


class LinkFolderResult(ApiModel):
    linked: bool
    files_catalogued: int
    skipped: int = 0                # files in the folder that were not taken (unknown type, duplicate, too big)
    commit: str | None = None
    version: str | None = None
