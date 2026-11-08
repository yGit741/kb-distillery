"""Agent proposals (mirrors kb_distillery.proposals.service)."""
from typing import Any, Literal

from kb_distillery.server.models.base import ApiModel

ProducerKind = Literal["manual", "chat", "flags", "ingest", "restructure", "lint", "restore"]
Status = Literal["open", "applied", "rejected", "stale"]
Decision = Literal["accept", "reject", "correct"]


class Producer(ApiModel):
    kind: ProducerKind = "manual"
    instruction: str = ""
    context: dict[str, Any] = {}


class ProposalOp(ApiModel):
    """One typed op. Fields by kind: edit_page {slug, new_text}, create_page {slug, text}, tombstone_page {slug,
    redirect_to}, rewrite_link {slug, from_slug, to_slug}, move_block {from_slug, to_slug, block_id}, set_frontmatter
    {slug, key, value}; every op may carry `reason` and `sources`."""
    kind: Literal["edit_page", "create_page", "tombstone_page", "rewrite_link", "move_block", "set_frontmatter"]
    id: str | None = None
    slug: str | None = None
    new_text: str | None = None
    text: str | None = None
    redirect_to: str | None = None
    from_slug: str | None = None
    to_slug: str | None = None
    block_id: str | None = None
    key: str | None = None
    value: str | None = None
    reason: str = ""
    sources: list[str] = []


class Finding(ApiModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    slug: str
    hunk_id: str | None = None
    source: str | None = None


class Hunk(ApiModel):
    id: str
    op_id: str
    op: str
    slug: str
    kind: Literal["prose", "structure"]
    before: str
    after: str
    tokens: list[list[str]]
    reason: str = ""
    sources: list[str] = []
    links_added: list[str] = []
    links_removed: list[str] = []
    at: int = 0
    span: int = 0


class Revision(ApiModel):
    n: int
    created: str
    note: str = ""
    ops: list[ProposalOp]
    hunks: list[Hunk]
    checks: list[Finding] = []


class HunkDecision(ApiModel):
    decision: Decision
    comment: str = ""
    at: str | None = None


class Checks(ApiModel):
    tier1: list[Finding] = []
    tier2: list[Finding] = []


class Applied(ApiModel):
    commit: str | None = None
    kb_version: str | None = None
    at: str
    hunks: list[str] = []


class Counts(ApiModel):
    hunks: int
    accepted: int
    rejected: int
    corrected: int


class CheckCounts(ApiModel):
    errors: int
    warnings: int
    blocking: int = 0


class ProducerKindOnly(ApiModel):
    kind: ProducerKind


class ProposalSummary(ApiModel):
    id: str
    title: str
    status: Status
    producer: ProducerKindOnly
    created: str
    updated: str
    pages: list[str]
    counts: Counts
    checks: CheckCounts


class ProposalList(ApiModel):
    proposals: list[ProposalSummary]


class Proposal(ApiModel):
    id: str
    title: str
    status: Status
    stale: bool
    stale_pages: list[str] = []
    producer: Producer
    created: str
    updated: str
    base: dict[str, str | None]
    revisions: list[Revision]
    current: int
    revision: int
    hunks: list[Hunk]
    decisions: dict[str, HunkDecision]
    checks: Checks
    counts: Counts
    check_counts: CheckCounts
    applied: Applied | None = None


class ProposalCreate(ApiModel):
    title: str
    producer: Producer = Producer()
    ops: list[ProposalOp]
    note: str | None = None


class RevisionCreate(ApiModel):
    ops: list[ProposalOp]
    note: str | None = None


class DecisionItem(ApiModel):
    hunk_id: str
    decision: Decision
    comment: str | None = None


class DecisionRequest(ApiModel):
    """One decision ({hunk_id, decision, comment?}) or a bulk form ({decisions: [...]})."""
    hunk_id: str | None = None
    decision: Decision | None = None
    comment: str | None = None
    decisions: list[DecisionItem] | None = None


class RejectRequest(ApiModel):
    reason: str | None = None


class ApplyResult(ApiModel):
    commit: str | None
    kb_version: str | None


class RenderHunk(ApiModel):
    id: str
    kind: str
    op: str
    at: int
    span: int


class RenderBlock(ApiModel):
    index: int
    kind: str
    text: str


class RenderPage(ApiModel):
    slug: str
    exists: bool
    text: str
    blocks: list[RenderBlock]
    my_notes: str = ""
    hunks: list[RenderHunk]


class ProposalRender(ApiModel):
    id: str
    revision: int
    stale: bool
    pages: list[RenderPage]
