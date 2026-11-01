"""GET /api/backlog — mirrors kb_distillery.services.backlog.list_items()."""
from kb_distillery.api.models.base import ApiModel


class BacklogDrift(ApiModel):
    level: str                 # fresh | drifted | stale | maybe-done | closed | none
    commits: int
    missing: list[str]
    maybe_done: list[str]


class BacklogItem(ApiModel):
    id: str
    title: str
    kind: str                  # idea | plan | bug
    area: str
    size: str                  # s | m | l
    status: str                # inbox | next | doing | done | dropped
    created: str
    source: str
    plan_status: str           # has-plan | no-plan
    base_sha: str
    branch: str
    paths: list[str]
    why: str
    drift: BacklogDrift


class BacklogList(ApiModel):
    items: list[BacklogItem]
    dir: str
