from kb_distillery.server.models.base import ApiModel


class KbImportGit(ApiModel):
    """JSON body of the import routes for a git source (the other form is a multipart upload: `file` is a .zip)."""
    git_url: str                    # https://, ssh:// or git@host:path, optional #ref
    id: str | None = None           # the new kb's id; absent = derived from the source name
    kit: str | None = None          # ontology kit; absent = the default


class KbImportPreview(ApiModel):
    """The dry run: what an import would do. Errors block it, warnings do not."""
    id: str
    name: str
    source: str                     # the zip's file name, or the git URL
    pages: int
    errors: list[str]
    warnings: list[str]
    ref: str
    commit: str
    ok: bool


class KbImportResult(ApiModel):
    id: str
    name: str
    root: str
    pages: int


class KbLibraryBundle(ApiModel):
    """One OKF bundle found in the knowledge library."""
    path: str
    name: str
    kind: str                       # "folder" or "zip"
    added: bool = False             # already the recorded import source of a knowledge base here


class KbLibrary(ApiModel):
    """The knowledge library (a local folder of bundles) and what a scan of it found."""
    path: str | None
    bundles: list[KbLibraryBundle]


class KbLibraryPut(ApiModel):
    path: str | None = None         # absolute folder; null or empty clears the library
