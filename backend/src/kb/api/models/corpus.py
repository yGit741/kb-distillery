"""Raw corpus tables, previews and the digest action (mirrors kb.services.corpus)."""

from kb.api.models.base import ApiModel


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


class DigestResult(ApiModel):
    exit: int
    stdout: str = ""
    stderr: str = ""
    command: str = ""


class ErrorBody(ApiModel):
    error: str
    formats: list[str] | None = None
