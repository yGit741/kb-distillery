"""Raw corpus tables, previews and the digest action (mirrors kb_distillery.services.corpus)."""

from kb_distillery.api.models.base import ApiModel


class CorpusColumn(ApiModel):
    key: str
    label: str


class CorpusRow(ApiModel):
    path: str
    disposition: str | None = None
    collection: list[str] = []
    slug: str | None = None
    digestion: str = ""                  # the depth of the page that cites the file ("" = none)
    year: int | None = None
    sha1: str = ""
    companion_of: str | None = None
    title: str = ""


class CorpusTable(ApiModel):
    format: str
    columns: list[CorpusColumn]
    rows: list[CorpusRow]
    count: int


class RawPreview(ApiModel):
    path: str
    exists: bool
    ext: str
    file_url: str
    format: str
    disposition: str | None = None
    slug: str | None = None
    collection: list[str] | None = None
    text: str = ""
    error: str | None = None


class RawFacts(ApiModel):
    bytes: int | None = None
    pages: int | None = None
    added: str | None = None


class ChatTurn(ApiModel):
    role: str
    text: str


class EmailHeader(ApiModel):
    sender: str | None = None
    date: str | None = None
    subject: str | None = None


class RawCard(ApiModel):
    """One raw file as a Home pipeline card (kb_distillery.services.raw_card); `thumb` is a data URI on share builds only."""
    path: str | None = None
    name: str | None = None
    format: str
    ext: str
    kind: str                            # pdf handwritten slides image web youtube chat email other
    facts: RawFacts
    title: str | None = None
    site: str | None = None
    url: str | None = None
    excerpt: str | None = None
    turns: list[ChatTurn] = []
    turn_count: int | None = None
    model: str | None = None
    header: EmailHeader | None = None
    video_id: str | None = None
    has_thumb: bool = False
    thumb: str | None = None


class DigestResult(ApiModel):
    exit: int
    stdout: str = ""
    stderr: str = ""
    command: str = ""


class ErrorBody(ApiModel):
    error: str
    formats: list[str] | None = None
