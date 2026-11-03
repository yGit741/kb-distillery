"""GET /api/ops — the Ops tab snapshot (nightly report model, runs, hygiene, threads, merge queue)."""
from typing import Any

from kb_distillery.server.models.base import ApiModel


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


class DeployState(ApiModel):
    live_sha: str | None = None
    live_at: str | None = None
    main_sha: str | None = None
    behind: bool | None = None          # None when live or main is unknown
    behind_minutes: int | None = None   # minutes since origin/main moved, while behind
    deploying: str | None = None
    last_outcome: str | None = None     # deployed | rolled-back | failed | rollback-failed
    last_sha: str | None = None
    last_reason: str = ""
    queued: list[str] = []
    rollbacks_7d: int = 0
    owner_installed: bool = False       # launchd plist present
    owner_alive: bool = False           # recent heartbeat (last_cycle_at)
    heartbeat_age: int | None = None    # seconds since the owner's last cycle


class OpsSnapshot(ApiModel):
    maintainer: bool = True             # the kb uses nightly / deploy-owner / a publisher; False hides those tiles
    subject: str | None = None
    doc: dict[str, Any] = {}
    queue: MergeQueue | None = None
    deploy: DeployState | None = None
