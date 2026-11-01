"""Model of GET /api/relations/proposals — LLM relation proposals, filterable by confidence (kb_distillery.services.relation_proposals)."""
from pydantic import ConfigDict, Field

from kb_distillery.api.models.base import ApiModel


class RelationProposal(ApiModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    from_: str = Field(alias="from")            # the JSON key is `from`, a Python keyword
    from_title: str
    to: str
    to_title: str
    kind: str
    confidence: float
    note: str = ""
    evidence: str = ""
    status: str                                 # "proposed" (accepted by the validator) or "low-confidence" (below 0.5)
    run: str = ""


class RelationProposals(ApiModel):
    rows: list[RelationProposal]
    total: int                                  # proposals of the chosen kind, any confidence
    shown: int                                  # rows inside the range
    kinds: list[str]
    histogram: list[int]                        # ten buckets of 0.1, all proposals of the chosen kind
