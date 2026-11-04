from kb_distillery.server.models.base import ApiModel


class KbInboxItem(ApiModel):
    """One upload on the site's inbox (the Worker's summary of it)."""
    item: str
    status: str                     # pending | imported | failed
    kind: str                       # zip | git
    at: str
    uploader: str
    kb_id: str | None = None
    kit: str | None = None
    pages: int = 0
    warnings: int = 0
    size: int = 0
    git_url: str | None = None
    error: str | None = None
    updated_at: str | None = None


class KbInbox(ApiModel):
    """The site's upload inbox. `configured` is false when this Mac has no site, token or bucket yet (not an error)."""
    configured: bool
    items: list[KbInboxItem] = []
    error: str = ""                 # the site could not be asked (unreachable, token refused); empty when it answered
    guide: str = ""                 # link to the set-up guide, when configured is false and this checkout knows its repo


class KbInboxOutcome(ApiModel):
    item: str
    kb_id: str = ""
    error: str = ""


class KbInboxPull(ApiModel):
    """What `pull` did: every pending item becomes a new kb, or fails with its reason."""
    imported: list[KbInboxOutcome]
    failed: list[KbInboxOutcome]
    unreported: list[str]           # done here, but the site did not take the news (it stays pending there)
