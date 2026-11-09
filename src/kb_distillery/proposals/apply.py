"""Apply a proposal: compose the accepted hunks onto the current pages and commit them as one knowledge step.

The step is a free-form ops session (`ops.core.begin` ... `commit`) with op `refine` (the kb's commit policy has a fixed
op list) and the summary `propose: <title> (<n> hunks)`. Pages are written only through `vault.wikiio.write_page`, so a
page's `## My notes` survives whatever the proposal says.
"""
from __future__ import annotations

import os

from kb_distillery.config.kb import ReadOnlyError, require_writable
from kb_distillery.git import commit_policy as cp
from kb_distillery.ops import core as ops
from kb_distillery.proposals import checks, diff
from kb_distillery.proposals.model import ProposalError, now, sha
from kb_distillery.vault import wikiio

OP = "refine"


def page_path(root, slug):
    return os.path.join(root, "wiki", f"{slug}.md")


def read_page(root, slug):
    p = page_path(root, slug)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def stale_slugs(root, proposal) -> list[str]:
    return [s for s, h in proposal["base"].items() if sha(read_page(root, s)) != h]


def accepted(proposal) -> set[str]:
    return {hid for hid, d in proposal["decisions"].items() if d.get("decision") == "accept"}


def apply(root: str, proposal: dict, auto: bool = False) -> dict:
    """Commit the accepted hunks; returns {commit, kb_version}. Mutates `proposal` (status, applied) for the caller to save."""
    if proposal["status"] not in ("open", "stale"):
        raise ProposalError(409, f"proposal is {proposal['status']}, not open")
    try:
        require_writable(root)
    except ReadOnlyError as e:
        raise ProposalError(405, str(e)) from None
    stale = stale_slugs(root, proposal)
    if stale:
        proposal["status"] = "stale"
        raise ProposalError(409, f"pages changed since the proposal was made: {', '.join(stale)} (stale; make a new revision)",
                            {"stale": stale})
    rev = proposal["revisions"][proposal["current"]]
    blocking = checks.blocking(proposal["checks"]["tier1"] + proposal["checks"]["tier2"], proposal["decisions"])
    if blocking:
        raise ProposalError(422, f"{len(blocking)} blocking check finding(s): fix them in a revision or reject their hunks",
                            {"blocking": blocking})
    ok = accepted(proposal) & {h["id"] for h in rev["hunks"]}
    if not ok:
        raise ProposalError(400, "no accepted hunk to apply")
    texts = diff.compose(proposal["base_texts"], rev["ops"], rev["hunks"], ok)
    if not texts:
        raise ProposalError(400, "the accepted hunks change nothing")
    summary = f"propose: {proposal['title']} ({len(ok)} hunks)"
    target = next(iter(texts))
    try:
        ops.begin(OP, target, summary, root=root)
    except ops.OpsError as e:
        raise ProposalError(409, f"cannot open the ops session: {e}") from None
    written = []
    try:
        for slug, text in texts.items():
            os.makedirs(os.path.dirname(page_path(root, slug)), exist_ok=True)
            wikiio.write_page(page_path(root, slug), text)
            written.append(slug)
        commit = ops.commit(summary, root=root)
    except Exception as e:                       # put the pages back as they were and close the session
        for slug in written:
            old = proposal["base_texts"].get(slug)
            if old is None:
                os.remove(page_path(root, slug))
            else:
                with open(page_path(root, slug), "w", encoding="utf-8", newline="") as f:
                    f.write(old)
        ops.abort(root=root)
        status = 409 if isinstance(e, ops.OpsError) else 500
        raise ProposalError(status, f"apply failed, pages restored: {e}") from None
    if not commit:
        raise ProposalError(409, "nothing changed on disk: no commit made, the proposal stays open")
    subject = ops._git(root, "log", "-1", "--format=%s").stdout.strip()
    m = cp.SUBJECT_KB.match(subject)
    version = f"kb-{subject.rsplit('(kb-', 1)[1].rstrip(')')}" if m else None
    proposal["status"] = "applied"
    proposal["applied"] = {"commit": commit, "kb_version": version, "at": now(), "hunks": sorted(ok), "auto": bool(auto),
                          "pages": sorted(texts)}
    return {"commit": commit, "kb_version": version}
