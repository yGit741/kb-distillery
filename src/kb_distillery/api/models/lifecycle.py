"""GET /api/lifecycle — mirrors kb_distillery.services.lifecycle.build_lifecycle_snapshot()."""
from typing import Literal

from pydantic import ConfigDict, Field

from kb_distillery.api.models.base import ApiModel

CommitKind = Literal["kb", "infra", "pr-merge", "sync-merge", "unknown"]


class TimelineRow(ApiModel):
    sha: str
    short: str
    date: str                                     # ISO 8601
    subject: str
    kind: str                                     # CommitKind; kept a str so a new kind never 500s
    type: str | None = None
    scope: str | None = None
    summary: str | None = None
    kb_version: str | None = None
    pr: int | None = None
    retro: bool = False
    parents: list[str] = []
    op: str | None = None
    target: str | None = None
    reverts: str | None = None
    reverted_by: str | None = None
    snapshot_tag: str | None = None


class SnapshotTag(ApiModel):
    tag: str
    date: str
    label: str


class InfraBranch(ApiModel):
    name: str
    date: str
    last: str
    ahead: int
    behind: int


class StaleWorktree(ApiModel):
    branch: str
    path: str
    merged: bool
    ahead: int | str
    dirty: int


class OpsSession(ApiModel):
    op: str
    target: str | None = None
    summary: str | None = None
    started: str | None = None


class Sessions(ApiModel):
    ingest: list[dict[str, str | None]]
    distill: list[dict[str, str | None]]
    researcher: list[str]
    ops: OpsSession | None = None


class WorkingState(ApiModel):
    lanes: dict[str, int]                         # knowledge / tooling / other
    knowledge: list[str]
    tooling: list[str]
    think_dirty: int
    sessions: Sessions
    unpushed: int | None = None


class NightlyState(ApiModel):
    plist_installed: bool
    log: str
    installed: bool | None = None
    loaded: bool | None = None
    last_run: str | None = None
    summary: str | None = None
    hint: str | None = None


class SchemaState(ApiModel):
    version: str
    applied: list[str]
    pending: list[str]


class PolicyState(ApiModel):
    hooks_installed: bool
    mode: str
    strict: bool


class LifecycleStats(ApiModel):
    kb_steps: int
    pr_merges: int
    ops_30d: dict[str, int]
    undone: int


class LifecycleSnapshot(ApiModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    generated_at: str
    branch: str
    head: str
    version: str | None = None
    next_version: str
    github: str | None = None
    schema_: SchemaState = Field(alias="schema")  # JSON key "schema" (BaseModel.schema is taken)
    policy: PolicyState
    timeline: list[TimelineRow]
    snapshots: list[SnapshotTag]
    stats: LifecycleStats
    # absent from a snapshot captured for the shared site
    working: WorkingState | None = None
    infra_branches: list[InfraBranch] | None = None
    nightly: NightlyState | None = None
    stale_worktrees: list[StaleWorktree] | None = None
