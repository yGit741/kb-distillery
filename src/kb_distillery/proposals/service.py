"""The HTTP-free entry points for proposals: create, revise, decide, apply, reject, read, render.

Producers (chat, flags, ingest, restructure, lint, restore) call `create` / `revise` with ops; the router adapts these
functions one to one. Failures are `ProposalError(status, message)`. `DEFAULT_ROOT` is the kb this process serves
(tests patch it); every function also takes `root=`.
"""
from __future__ import annotations

from kb_distillery.config.kb import ReadOnlyError, require_writable
from kb_distillery.config.paths import vault_root
from kb_distillery.proposals import apply as applier
from kb_distillery.proposals import checks, diff, store
from kb_distillery.proposals.model import (DECISIONS, ProposalError, new_id, now, sha, touched_slugs, validate_ops,
                                           validate_producer)

DEFAULT_ROOT = vault_root()


def _root(root):
    return root or DEFAULT_ROOT


def _writable(root):
    root = _root(root)
    try:
        require_writable(root)
    except ReadOnlyError as e:
        raise ProposalError(405, str(e)) from None
    return root


def _revision(root, ops, note, n):
    """(revision, base, base_texts): hunks and tier-1 findings against the pages as they are now."""
    ops = validate_ops(ops)
    base_texts = {s: applier.read_page(root, s) for s in touched_slugs(ops)}
    hunks, results = diff.build(base_texts, ops)
    findings = checks.tier1(root, hunks, {s: t for s, t in results.items() if t != base_texts.get(s)})
    rev = {"n": n, "created": now(), "note": str(note or ""), "ops": ops, "hunks": hunks, "checks": findings}
    return rev, {s: sha(t) for s, t in base_texts.items()}, base_texts


def _counts(p):
    rev = p["revisions"][p["current"]]
    ids = {h["id"] for h in rev["hunks"]}
    decided = [d["decision"] for hid, d in p["decisions"].items() if hid in ids]
    found = p["checks"]["tier1"] + p["checks"]["tier2"]
    return ({"hunks": len(ids), "accepted": decided.count("accept"), "rejected": decided.count("reject"),
             "corrected": decided.count("correct")},
            {"errors": sum(f["severity"] == "error" for f in found),
             "warnings": sum(f["severity"] == "warning" for f in found),
             "blocking": len(checks.blocking(found, p["decisions"]))})


def summary(p) -> dict:
    counts, found = _counts(p)
    return {"id": p["id"], "title": p["title"], "status": p["status"], "producer": {"kind": p["producer"]["kind"]},
            "created": p["created"], "updated": p["updated"], "pages": list(p["base"]), "counts": counts,
            "checks": found}


def full(p, root=None) -> dict:
    """The proposal as the API returns it: current revision's hunks on top, stale recomputed (not saved)."""
    root = _root(root)
    out = {k: v for k, v in p.items() if k != "base_texts"}
    if out["status"] in ("open", "stale"):
        stale = applier.stale_slugs(root, p)
        out["status"] = "stale" if stale else "open"
        out["stale_pages"] = stale
    else:
        out["stale_pages"] = []
    out["stale"] = out["status"] == "stale"
    rev = p["revisions"][p["current"]]
    out["revision"] = rev["n"]
    out["hunks"] = rev["hunks"]
    out["counts"], out["check_counts"] = _counts(p)
    return out


def list_proposals(status=None, root=None) -> list[dict]:
    root = _root(root)
    out = []
    for pid in store.all_ids(root):
        p = store.load(root, pid)
        s = summary(p)
        if p["status"] in ("open", "stale"):
            s["status"] = "stale" if applier.stale_slugs(root, p) else "open"
        if not status or s["status"] == status:
            out.append(s)
    return sorted(out, key=lambda s: s["updated"], reverse=True)


def get(pid, root=None) -> dict:
    root = _root(root)
    return full(store.load(root, pid), root)


def create(title, ops, producer=None, note=None, root=None) -> dict:
    root = _writable(root)
    title = " ".join(str(title or "").split())
    if not title:
        raise ProposalError(400, "title is required")
    producer = validate_producer(producer)
    rev, base, base_texts = _revision(root, ops, note, 1)
    stamp = now()
    p = {"id": new_id(), "kb_root": root, "title": title, "producer": producer, "created": stamp, "updated": stamp,
         "status": "open", "base": base, "base_texts": base_texts, "revisions": [rev], "current": 0,
         "decisions": {}, "checks": {"tier1": rev["checks"], "tier2": []}, "applied": None}
    store.save(root, p)
    return full(p, root)


def _open(root, pid):
    p = store.load(root, pid)
    if p["status"] not in ("open", "stale"):
        raise ProposalError(409, f"proposal is {p['status']}")
    return p


def revise(pid, ops, note=None, root=None) -> dict:
    """A new revision against the pages as they are now; decisions survive for hunks whose content is identical."""
    root = _writable(root)
    p = _open(root, pid)
    rev, base, base_texts = _revision(root, ops, note, len(p["revisions"]) + 1)
    ids = {h["id"] for h in rev["hunks"]}
    p["decisions"] = {hid: d for hid, d in p["decisions"].items() if hid in ids}
    p["revisions"].append(rev)
    p.update(current=len(p["revisions"]) - 1, base=base, base_texts=base_texts, status="open", updated=now(),
             checks={"tier1": rev["checks"], "tier2": []})
    store.save(root, p)
    return full(p, root)


def decide(pid, decisions, root=None) -> dict:
    """`decisions` = [{hunk_id, decision, comment?}]; each replaces the hunk's earlier decision."""
    root = _writable(root)
    p = _open(root, pid)
    ids = {h["id"] for h in p["revisions"][p["current"]]["hunks"]}
    if not decisions:
        raise ProposalError(400, "no decision given")
    for d in decisions:
        hid, dec = d.get("hunk_id"), d.get("decision")
        if hid not in ids:
            raise ProposalError(404, f"no hunk {hid!r} in the current revision")
        if dec not in DECISIONS:
            raise ProposalError(400, f"decision {dec!r} is not one of {', '.join(DECISIONS)}")
        p["decisions"][hid] = {"decision": dec, "comment": str(d.get("comment") or ""), "at": now()}
    p["updated"] = now()
    store.save(root, p)
    return full(p, root)


def apply(pid, root=None) -> dict:
    root = _writable(root)
    p = store.load(root, pid)
    try:
        out = applier.apply(root, p)
    finally:
        p["updated"] = now()
        store.save(root, p)                      # a stale mark or the applied record, either way kept
    return out


def reject(pid, reason=None, root=None) -> dict:
    root = _writable(root)
    p = _open(root, pid)
    p.update(status="rejected", rejected={"reason": str(reason or ""), "at": now()}, updated=now())
    store.save(root, p)
    return full(p, root)


def render(pid, root=None) -> dict:
    """Each touched page as it is now, with the current revision's hunks positioned by block index."""
    root = _root(root)
    p = store.load(root, pid)
    rev = p["revisions"][p["current"]]
    current = {s: applier.read_page(root, s) for s in p["base"]}
    return {"id": p["id"], "revision": rev["n"], "stale": bool(applier.stale_slugs(root, p)),
            "pages": diff.render(current, rev["hunks"])}
