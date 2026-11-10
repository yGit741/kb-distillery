"""The HTTP-free entry points for proposals: create, revise, decide, apply, reject, read, render.

Producers (chat, flags, ingest, restructure, lint, restore) call `create` / `revise` with ops; the router adapts these
functions one to one. Failures are `ProposalError(status, message)`. `DEFAULT_ROOT` is the kb this process serves
(tests patch it); every function also takes `root=`.
"""
from __future__ import annotations

import subprocess

from kb_distillery.config.kb import ReadOnlyError, require_writable
from kb_distillery.config.paths import vault_root
from kb_distillery.proposals import apply as applier
from kb_distillery.ops import core as opscore
from kb_distillery.proposals import checks, checks_semantic, diff, store, trust
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


def _klass(h):
    return h.get("klass") or trust.classify_hunk(h)


def _premark(root, p):
    """Hunks of an auto-apply class without a decision get a `suggested` accept the UI can show (one click to keep)."""
    cfg = trust.tiers(root)
    for h in p["revisions"][p["current"]]["hunks"]:
        if h["id"] not in p["decisions"] and trust.tier_of(_klass(h), cfg) == "auto_apply":
            p["decisions"][h["id"]] = {"decision": "accept", "comment": "", "suggested": True, "at": now()}


def _auto_ok(root, p):
    """True when every hunk is an auto-apply class and tier 1 found no error."""
    hunks = p["revisions"][p["current"]]["hunks"]
    cfg = trust.tiers(root)
    return (bool(hunks) and all(trust.tier_of(_klass(h), cfg) == "auto_apply" for h in hunks)
            and not any(f["severity"] == "error" for f in p["checks"]["tier1"]))


def _finish(root, p, auto):
    """After a new revision: pre-mark the boring hunks; apply the whole proposal when the producer asked and it is all boring."""
    p = store.load(root, p["id"])
    _premark(root, p)
    store.save(root, p)
    if auto and _auto_ok(root, p):
        try:
            apply(p["id"], root, auto=True)
        except ProposalError:
            pass                                   # stays open with its suggested accepts for the owner
    return full(store.load(root, p["id"]), root)


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


def summary(p, cfg=None, stale=None) -> dict:
    """The list row: counts, the hunk classes and trust tiers of the current revision, the pages that changed since."""
    counts, found = _counts(p)
    hunks = p["revisions"][p["current"]]["hunks"]
    cfg = cfg or {"auto_apply": [], "review": [], "explicit": []}
    classes, tiers = {}, {"auto_apply": 0, "review": 0, "explicit": 0}
    for h in hunks:
        k = _klass(h)
        classes[k] = classes.get(k, 0) + 1
        tiers[trust.tier_of(k, cfg)] += 1
    return {"id": p["id"], "title": p["title"], "status": p["status"], "producer": {"kind": p["producer"]["kind"]},
            "created": p["created"], "updated": p["updated"], "pages": list(p["base"]), "counts": counts,
            "checks": found, "classes": classes, "tiers": tiers, "stale_pages": stale or [],
            "top_class": top_class(classes)}


# riskiest first: what the owner has to read before the boring link fixes
CLASS_ORDER = ("claims", "structure", "new_page", "tombstone", "split", "merge", "rename", "links", "format", "typos")


def top_class(classes) -> str:
    rank = {k: i for i, k in enumerate(CLASS_ORDER)}
    return min(classes, key=lambda k: rank.get(k, len(rank)), default="")


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
    out["hunks"] = [h if h.get("klass") else dict(h, klass=_klass(h)) for h in rev["hunks"]]
    out["counts"], out["check_counts"] = _counts(p)
    return out


STATUS_FILTERS = {"open": ("open", "stale"), "stale": ("stale",), "applied": ("applied",), "undone": ("undone",),
                  "rejected": ("rejected",)}
GROUPS = ("page", "class", "time")


def _groups(rows, group):
    """[{key, label, count, proposals}] for `group` in page | class | time; a multi-page proposal sits under each page,
    otherwise a proposal sits once (class: under its riskiest class; time: under the day it was last updated)."""
    buckets: dict[str, list[dict]] = {}
    for s in rows:
        if group == "page":
            keys = s["pages"] or [""]
        elif group == "class":
            keys = [s["top_class"] or "other"]
        else:
            keys = [(s["updated"] or "")[:10]]
        for k in keys:
            buckets.setdefault(k, []).append(s)
    if group == "class":
        rank = {k: i for i, k in enumerate(CLASS_ORDER)}
        order = sorted(buckets, key=lambda k: (rank.get(k, len(rank)), k))
    elif group == "time":
        order = sorted(buckets, reverse=True)
    else:
        order = sorted(buckets, key=lambda k: (-len(buckets[k]), k))
    return [{"key": k, "label": k, "count": len(buckets[k]), "proposals": buckets[k]} for k in order]


def inbox(status=None, root=None, group=None) -> dict:
    """{proposals, groups}: newest first. `status`: open (open + stale) | applied | undone | rejected | stale | all (or none).
    `groups` is filled only when `group` is page | class | time."""
    root = _root(root)
    if status in (None, "", "all"):
        want = None
    elif status in STATUS_FILTERS:
        want = STATUS_FILTERS[status]
    else:
        raise ProposalError(400, f"status {status!r} is not one of all, {', '.join(STATUS_FILTERS)}")
    if group and group not in GROUPS:
        raise ProposalError(400, f"group {group!r} is not one of {', '.join(GROUPS)}")
    cfg = trust.tiers(root)
    out = []
    for pid in store.all_ids(root):
        p = store.load(root, pid)
        stale = applier.stale_slugs(root, p) if p["status"] in ("open", "stale") else []
        s = summary(p, cfg, stale)
        if p["status"] in ("open", "stale"):
            s["status"] = "stale" if stale else "open"
        if want is None or s["status"] in want:
            out.append(s)
    out.sort(key=lambda s: s["updated"], reverse=True)
    return {"proposals": out, "groups": _groups(out, group) if group else []}


def list_proposals(status=None, root=None) -> list[dict]:
    return inbox(status, root)["proposals"]


def get(pid, root=None) -> dict:
    root = _root(root)
    return full(store.load(root, pid), root)


def create(title, ops, producer=None, note=None, root=None, semantic=False, backend=None, auto=False) -> dict:
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
    return _finish(root, _maybe_semantic(root, p, semantic, backend), auto)


def _maybe_semantic(root, p, semantic, backend):
    """Tier 2 right after tier 1 when asked; a failed model call leaves an info finding, never a failed request."""
    if not semantic:
        return p
    try:
        checks_semantic.run(root, p["id"], backend)
    except Exception as e:  # noqa: BLE001  (the proposal is saved; a failed review must not fail the request)
        p = store.load(root, p["id"])
        rev = p["revisions"][p["current"]]
        slug = rev["hunks"][0]["slug"] if rev["hunks"] else (rev["ops"][0].get("slug") or "")
        p["checks"]["tier2"] = [checks.finding("info", "semantic-unavailable", f"semantic check not run: {e}", slug,
                                               source="tier2")]
        store.save(root, p)
    return store.load(root, p["id"])


def semantic(pid, backend=None, root=None) -> dict:
    """Run the tier-2 scoped semantic check on the current revision (synchronous); returns {findings, revision}."""
    root = _writable(root)
    return checks_semantic.run(root, pid, backend)


def _open(root, pid):
    p = store.load(root, pid)
    if p["status"] not in ("open", "stale"):
        raise ProposalError(409, f"proposal is {p['status']}")
    return p


def _install(root, p, rev, base, base_texts, semantic, backend, auto):
    """Make `rev` the proposal's current revision; decisions survive for hunks whose content-based id is unchanged."""
    ids = {h["id"] for h in rev["hunks"]}
    p["decisions"] = {hid: d for hid, d in p["decisions"].items() if hid in ids}
    p["revisions"].append(rev)
    p.update(current=len(p["revisions"]) - 1, base=base, base_texts=base_texts, status="open", updated=now(),
             checks={"tier1": rev["checks"], "tier2": []})
    store.save(root, p)
    return _finish(root, _maybe_semantic(root, p, semantic, backend), auto)


def revise(pid, ops, note=None, root=None, semantic=False, backend=None, auto=False) -> dict:
    """A new revision against the pages as they are now; decisions survive for hunks whose content is identical."""
    root = _writable(root)
    p = _open(root, pid)
    rev, base, base_texts = _revision(root, ops, note, len(p["revisions"]) + 1)
    return _install(root, p, rev, base, base_texts, semantic, backend, auto)


def _dropped(h, why):
    return {"hunk_id": h["id"], "slug": h["slug"], "klass": _klass(h), "op": h["op"], "before": h["before"],
            "after": h["after"], "reason": why}


def rebase(pid, root=None) -> dict:
    """Recompute the hunks of an open proposal against the pages as they are now.

    Edits are re-applied where their before text still sits; a hunk whose before text vanished is dropped and listed
    (`dropped`, also kept on the new revision). Decisions on surviving hunks stay (hunk ids are content-based).
    Returns {proposal, dropped}; 409 when nothing survives (reject the proposal instead)."""
    root = _writable(root)
    p = _open(root, pid)
    rev = p["revisions"][p["current"]]
    stale = set(applier.stale_slugs(root, p))
    if not stale:
        return {"proposal": full(p, root), "dropped": []}
    dropped, ops = [], []
    for op in diff._order(rev["ops"]):
        mine = [h for h in rev["hunks"] if h["op_id"] == op["id"]]
        slug = op.get("slug")
        if slug not in stale and not (op["kind"] == "move_block" and {op["from_slug"], op["to_slug"]} & stale):
            ops.append(op)
            continue
        current = applier.read_page(root, slug) if slug else None
        if op["kind"] == "edit_page":
            if current is None:
                dropped += [_dropped(h, "the page no longer exists") for h in mine]
                continue
            text, gone = diff.rebase_edit(p["base_texts"].get(slug) or "", current, mine)
            dropped += [_dropped(h, "the text it changed is no longer on the page") for h in gone]
            if len(gone) < len(mine):
                ops.append(dict(op, new_text=text))
            continue
        if op["kind"] == "create_page" and current is not None:
            dropped += [_dropped(h, "the page now exists") for h in mine]
            continue
        try:                                        # set_frontmatter / rewrite_link / tombstone: keep when still valid
            texts = {s: applier.read_page(root, s) for s in touched_slugs(ops + [op])}
            diff.build(texts, ops + [op])
        except ProposalError as e:
            dropped += [_dropped(h, str(e)) for h in mine]
            continue
        ops.append(op)
    if not ops:
        raise ProposalError(409, "nothing of this proposal still applies to the changed pages: reject it",
                            {"dropped": dropped})
    new_rev, base, base_texts = _revision(root, [{k: v for k, v in o.items() if k != "id"} for o in ops],
                                          "rebased onto the current pages", len(p["revisions"]) + 1)
    new_rev["dropped"] = dropped
    return {"proposal": _install(root, p, new_rev, base, base_texts, False, None, False), "dropped": dropped}


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


def apply(pid, root=None, auto=False) -> dict:
    root = _writable(root)
    p = store.load(root, pid)
    if auto:                                       # auto-apply accepts what it applies, as suggested decisions
        for h in p["revisions"][p["current"]]["hunks"]:
            p["decisions"].setdefault(h["id"], {"decision": "accept", "comment": "", "suggested": True, "at": now()})
    try:
        out = applier.apply(root, p, auto=auto)
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


def suggestions(root=None) -> list[dict]:
    """The nightly tier-3 suggestions that carry no edit (the review inbox lists them next to the proposals)."""
    from kb_distillery.proposals import nightly
    return nightly.list_suggestions(_root(root))


def trust_tiers(root=None) -> dict:
    """The kb's effective trust tiers: {auto_apply, review, explicit, source: "kb.toml" | "default"}."""
    return trust.tiers(_root(root))


def _blockers(root, p):
    """Later first-parent commits that changed a page this proposal's commit wrote (a page back at the
    state of that commit, for example after an undo of the later step, is no blocker): [{slug, commits: ["abc1234 subject"]}]."""
    commit = (p.get("applied") or {}).get("commit")
    pages = (p.get("applied") or {}).get("pages") or list(p["base"])
    if not commit:
        return None
    out = []
    for slug in pages:
        proc = opscore._git(root, "log", "--first-parent", "--format=%h %s", f"{commit}..HEAD", "--", f"wiki/{slug}.md")
        if proc.returncode != 0:
            return None
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if lines and opscore._blob(root, "HEAD", f"wiki/{slug}.md") != opscore._blob(root, commit, f"wiki/{slug}.md"):
            out.append({"slug": slug, "commits": lines})
    return out


def feed(since=None, root=None) -> list[dict]:
    """Applied (and undone) proposals, newest first: what changed without or after review, and whether it can be undone."""
    root = _root(root)
    out = []
    for pid in store.all_ids(root):
        p = store.load(root, pid)
        ap = p.get("applied")
        if p["status"] not in ("applied", "undone") or not ap:
            continue
        if since and ap["at"] < since:
            continue
        rev = p["revisions"][p["current"]]
        used = [h for h in rev["hunks"] if h["id"] in set(ap.get("hunks") or [h["id"] for h in rev["hunks"]])]
        blockers = _blockers(root, p) if p["status"] == "applied" else None
        item = {"id": p["id"], "title": p["title"], "status": p["status"], "pages": ap.get("pages") or list(p["base"]),
                "hunks": len(used), "classes": sorted({_klass(h) for h in used}), "applied_at": ap["at"],
                "commit": ap.get("commit"), "auto": bool(ap.get("auto")), "undoable": blockers == [] and p["status"] == "applied",
                "blocked_by": [b["slug"] for b in blockers or []]}
        if p.get("undone"):
            item["undone_at"] = p["undone"]["at"]
        out.append(item)
    return sorted(out, key=lambda i: i["applied_at"], reverse=True)


def undo(pid, root=None) -> dict:
    """Revert the one commit this proposal made (ops undo); 409 naming the pages when later commits touched them."""
    root = _writable(root)
    p = store.load(root, pid)
    if p["status"] == "undone":
        raise ProposalError(409, "proposal was already undone")
    if p["status"] != "applied" or not (p.get("applied") or {}).get("commit"):
        raise ProposalError(409, f"proposal is {p['status']}, there is nothing to undo")
    blockers = _blockers(root, p)
    if blockers is None:
        raise ProposalError(409, "cannot read the history of the applied commit")
    if blockers:
        names = ", ".join(b["slug"] for b in blockers)
        raise ProposalError(409, f"later commits changed the same pages: {names}; undo or resolve those first",
                            {"pages": [b["slug"] for b in blockers], "blockers": blockers})
    try:
        commit = opscore.undo(p["applied"]["commit"], root=root)
    except (opscore.OpsError, subprocess.CalledProcessError) as e:
        raise ProposalError(409, f"undo refused: {e}") from None
    p.update(status="undone", undone={"at": now(), "commit": commit if isinstance(commit, str) else None}, updated=now())
    store.save(root, p)
    return full(p, root)


def dismiss_suggestion(sid, root=None) -> dict:
    from kb_distillery.proposals import nightly
    return nightly.dismiss_suggestion(_writable(root), sid)
