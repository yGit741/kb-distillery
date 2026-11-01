"""Think notes: the human's own notes under think/, edited in the Think screen."""
from kb_distillery.api.models.base import ApiModel


class ThinkNoteMeta(ApiModel):
    name: str
    size: int
    mtime: float


class ThinkList(ApiModel):
    notes: list[ThinkNoteMeta]
    capture_note: str


class ThinkNote(ApiModel):
    name: str
    text: str
    mtime: float


class ThinkSaveRequest(ApiModel):
    text: str
    base_mtime: float | None = None
    create: bool | None = None  # None = plain save (optional in the generated client)


class ThinkWriteResult(ApiModel):
    name: str
    mtime: float
    created: bool


class ThinkCaptureRequest(ApiModel):
    text: str
