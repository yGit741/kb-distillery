"""GET /api/ops — the Ops tab snapshot (nightly report model, runs, hygiene, threads, merge queue)."""
from typing import Any

from kb.api.models.base import ApiModel


class QueueEntry(ApiModel):
    pr: int | str | None = None
    branch: str | None = None
    pid: int | None = None
    host: str | None = None
    age: int = 0          # seconds since it joined the queue
    held: int = 0         # seconds since its last heartbeat (holder: time holding the lock)
    alive: bool | None = None   # None when the pid lives on another host
    stale: bool = False


class MergeQueue(ApiModel):
    holder: QueueEntry | None = None
    waiters: list[QueueEntry] = []
    stale_after: int = 1200


class OpsSnapshot(ApiModel):
    subject: str | None = None
    doc: dict[str, Any] = {}
    queue: MergeQueue | None = None
