"""Agent proposals: an agent change to the wiki is never written directly, it becomes a proposal the owner reviews.

A proposal is a list of typed operations (`model.OP_KINDS`) across one or more pages, kept as revisions (v1, v2, ...).
The core, not the producer, cuts each revision into hunks (`diff`), runs the tier-1 checks on it (`checks`), records
the owner's per-hunk decisions and applies the accepted hunks as one knowledge step through `ops.core.begin/commit`
(`apply`). Proposals are JSON files in `<kb>/.local/proposals/<id>.json` (`store`). The HTTP-free entry points the
router and later producers call are in `service`. Docs: src/kb_distillery/kits/base/defaults/docs/proposals.md.
"""
from kb_distillery.proposals.model import OP_KINDS, PRODUCER_KINDS, ProposalError

__all__ = ["OP_KINDS", "PRODUCER_KINDS", "ProposalError"]
