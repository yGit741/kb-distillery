"""The Review deck: every open proposal cut into one card per hunk, plus the deck's own actions.

`deck` lists the cards (riskiest class first, a dropped source's cards together). Decisions stay in the browser
until Apply, so a card can be taken back any number of times; `apply_batch` then records them per proposal and
applies what is fully decided: all rejected -> the proposal is rejected, some accepted -> applied, any card left for
later -> the proposal waits. `rewrite` turns one owner sentence into a new revision that changes only that card's
text (one model call); `split` asks the model where to cut a page and makes the restructure proposal.
"""
from __future__ import annotations

from kb_distillery import llm
from kb_distillery.proposals import diff, restructure, service, store, trust
from kb_distillery.proposals.model import ProposalError
from kb_distillery.vault import graph, links, wikiio
from kb_distillery.vault.pages import load_wiki_pages

REWRITABLE = ("edit_page", "create_page")
CONTEXT_CHARS = 1200
PAGE_CHARS = 16000
SYSTEM = "You revise one proposed change to a wiki page on the owner's request. Reply with one JSON object and nothing else."
SPLIT_SYSTEM = "You split one wiki page into focused pages. Reply with one JSON object and nothing else."


def _root(root):
    return root or service.DEFAULT_ROOT


def _context(text, at, span):
    """(block before, block after) a hunk at block `at` covering `span` blocks; frontmatter never counts as context."""
    if text is None:
        return "", ""
    blocks = diff.split_blocks(wikiio.strip_my_notes(text))
    before = blocks[at - 1] if 0 < at <= len(blocks) else None
    after = blocks[at + span] if at + span < len(blocks) else None
    pick = lambda b: "" if b is None or b["kind"] == diff.FM else b["raw"].strip()[:CONTEXT_CHARS]  # noqa: E731
    return pick(before), pick(after)


def _findings(p, h):
    found = p["checks"]["tier1"] + p["checks"]["tier2"]
    return [f for f in found if f.get("slug") in (None, "", h["slug"]) and f.get("hunk_id") in (None, "", h["id"])]


def _group(p):
    """The deck groups a dropped source's cards: the raw path for ingest, else the proposal itself."""
    ctx = p["producer"].get("context") or {}
    return f"source:{ctx['source']}" if p["producer"]["kind"] == "ingest" and ctx.get("source") else f"proposal:{p['id']}"


REACH_CAP = 40


def _reach(h, pages, inbound, titles):
    """The card's blast radius: the pages that link to its page (they lean on what it says), the pages it links to,
    and the links this change adds or removes. {total, pages: [{slug, title, type, rel, exists}]} with `rel` one of
    added | removed | in | out; the list is capped, `total` is not."""
    slug = h["slug"]
    text = pages[slug][2] if slug in pages else (h["after"] if h["op"] == "create_page" else "")
    fm = pages[slug][1] if slug in pages else None
    added, removed = set(h.get("links_added") or []), set(h.get("links_removed") or [])
    out = set(graph.outbound_links(text, fm)) if text else set()
    if h["op"] == "create_page":
        out |= set(graph.outbound_links(h["after"]))
    rel = {}
    for s in inbound.get(slug, ()):
        rel[s] = "in"
    for s in out:
        rel.setdefault(s, "out")
    for s in removed:
        rel[s] = "removed"
    for s in added:
        rel[s] = "added"
    rel.pop(slug, None)
    order = {"added": 0, "removed": 1, "in": 2, "out": 3}
    items = sorted(rel.items(), key=lambda kv: (order[kv[1]], titles.get(kv[0], kv[0]).lower()))
    kind = lambda s: str(pages[s][1].get("type") or "concept") if s in pages else "concept"  # noqa: E731
    return {"total": len(items), "pages": [{"slug": s, "title": titles.get(s, s), "type": kind(s), "rel": r, "exists": s in pages}
                                           for s, r in items[:REACH_CAP]]}


def deck(root=None) -> dict:
    """{cards, proposals}: one card per hunk of every open (or stale) proposal; `decision` is the server's, if any;
    `reach` is the card's blast radius in the wiki's link graph."""
    root = _root(root)
    cfg = trust.tiers(root)
    pages = load_wiki_pages(root)
    inbound = graph.inbound_index(pages)
    titles = {s: str(fm.get("title") or s) for s, (_rel, fm, _text) in pages.items()}
    rank = {k: i for i, k in enumerate(service.CLASS_ORDER)}
    cards, proposals = [], []
    for pid in store.all_ids(root):
        p = store.load(root, pid)
        if p["status"] not in ("open", "stale"):
            continue
        full = service.full(p, root)
        ctx = p["producer"].get("context") or {}
        proposals.append({"id": pid, "title": p["title"], "producer": p["producer"]["kind"],
                          "instruction": p["producer"].get("instruction", ""), "source": ctx.get("source", ""),
                          "stale": full["stale"], "stale_pages": full["stale_pages"], "updated": p["updated"],
                          "hunks": len(full["hunks"]), "group": _group(p)})
        for h in full["hunks"]:
            base = p["base_texts"].get(h["slug"])
            before, after = _context(base, h["at"], h["span"]) if h["op"] == "edit_page" else ("", "")
            klass = h.get("klass") or trust.classify_hunk(h)
            title = links.title_of(base or (h["after"] if h["op"] == "create_page" else ""), h["slug"])
            cards.append({"id": f"{pid}:{h['id']}", "proposal_id": pid, "hunk": h, "klass": klass,
                          "tier": trust.tier_of(klass, cfg), "page_title": title, "context_before": before,
                          "context_after": after, "decision": p["decisions"].get(h["id"]),
                          "findings": _findings(p, h), "stale": full["stale"], "group": _group(p),
                          "producer": p["producer"]["kind"], "source": ctx.get("source", ""),
                          "updated": p["updated"], "reach": _reach(h, pages, inbound, titles)})
    # a dropped source's new pages first, then claims, then the boring classes; newest proposal first within a class
    cards.sort(key=lambda c: c["updated"], reverse=True)
    cards.sort(key=lambda c: (rank.get(c["klass"], len(rank)), c["hunk"]["slug"], c["hunk"]["at"]))
    return {"cards": cards, "proposals": proposals}


# -- rewrite one card ----------------------------------------------------------------------------------------------------
def _trailing(s):
    return s[len(s.rstrip()):]


def _splice_edit(base, new_text, k, replacement):
    """`new_text` (the op's page) with the k-th changed block run (in diff order against `base`) replaced."""
    new = wikiio.preserve_my_notes(base, new_text)
    old_blocks = diff.split_blocks(wikiio.strip_my_notes(base))
    new_blocks = diff.split_blocks(wikiio.strip_my_notes(new))
    runs = [oc for oc in diff._opcodes(old_blocks, new_blocks) if oc[0] != "equal"]
    if k >= len(runs):
        raise ProposalError(409, "the card no longer matches its proposal: reload the deck")
    _tag, _i1, _i2, j1, j2 = runs[k]
    parts = [b["raw"] for b in new_blocks[:j1]] + [replacement] + [b["raw"] for b in new_blocks[j2:]]
    return wikiio.preserve_my_notes(base, "".join(parts))


MARKS_CAP = 8
MARK_CHARS = 1500


def _marks(marks):
    """The owner's highlighted passages, trimmed and de-duplicated, at most MARKS_CAP."""
    out = []
    for m in marks or []:
        m = " ".join(str(m or "").split())[:MARK_CHARS]
        if m and m not in out:
            out.append(m)
    return out[:MARKS_CAP]


PAGES_CAP = 8
PAGE_CTX_CHARS = 1500


def _page_context(root, slugs):
    """[(slug, title, excerpt)] for the pages the owner picked in the graph (existing pages only, at most PAGES_CAP)."""
    pages = load_wiki_pages(root)
    out = []
    for slug in dict.fromkeys(str(s) for s in slugs or []):
        if slug in pages and len(out) < PAGES_CAP:
            _rel, fm, text = pages[slug]
            body = links.body_of(wikiio.strip_my_notes(text)).strip()
            out.append((slug, str(fm.get("title") or slug), body[:PAGE_CTX_CHARS]))
    return out


def rewrite_prompt(title, slug, before_ctx, h, instruction, sources, marks=(), pages=()):
    was = h["before"] if h["op"] == "edit_page" else "(a new page)"
    focus = ("The owner highlighted these passages; the request is about them:\n"
             + "\n".join(f"- \"{m}\"" for m in marks) + "\n\n") if marks else ""
    if pages:
        focus += ("The owner picked these related pages as context (link them as [Title](slug.md) when the request "
                  "asks for it):\n" + "\n\n".join(f"## {t} (`{s}`)\n{x}" for s, t, x in pages) + "\n\n")
    return (f"Page `{slug}` ({title}).\n\n"
            f"Text just before the change:\n{before_ctx or '(start of page)'}\n\n"
            f"The page says now:\n{was}\n\n"
            f"The proposed change would make it:\n{h['after'][:PAGE_CHARS]}\n\n"
            f"Sources the change cites: {', '.join(sources) or '(none)'}\n\n"
            f"{focus}The owner asks: {instruction}\n\n"
            "Rewrite the PROPOSED text so it does what the owner asks. Keep markdown, links, footnote markers "
            "([^id]) and frontmatter keys unless the owner asks otherwise; never invent a source. Reply as JSON:\n"
            '{"reply": "one calm sentence: what you changed", "after": "the full new proposed text"}')


def _parse_rewrite(raw):
    obj = llm.json_object(raw) or {}
    after = obj.get("after")
    return str(obj.get("reply") or "").strip(), (after if isinstance(after, str) else None)


def rewrite(pid, hunk_id, instruction, backend=None, root=None, marks=None, pages=None) -> dict:
    """A new revision in which only this card's proposed text follows `instruction` (about the `marks` the owner
    highlighted and the `pages` picked in the graph, when given); returns
    {proposal, reply, hunk_id (the card's new hunk), others_changed (other hunk ids that did not survive)}."""
    root = _root(root)
    instruction = " ".join(str(instruction or "").split())
    if not instruction:
        raise ProposalError(400, "say what should change")
    p = store.load(root, pid)
    if p["status"] not in ("open", "stale"):
        raise ProposalError(409, f"proposal is {p['status']}")
    rev = p["revisions"][p["current"]]
    h = next((x for x in rev["hunks"] if x["id"] == hunk_id), None)
    if h is None:
        raise ProposalError(404, f"no card {hunk_id!r} in the current revision: reload the deck")
    op = next(o for o in rev["ops"] if o["id"] == h["op_id"])
    if op["kind"] not in REWRITABLE:
        raise ProposalError(400, "this kind of change (a link rewrite, a key, a retired page) cannot be rewritten: "
                                 "accept or reject it")
    base = p["base_texts"].get(h["slug"])
    title = links.title_of(base or op.get("text") or "", h["slug"])
    before_ctx, _ = _context(base, h["at"], h["span"]) if op["kind"] == "edit_page" else ("", "")
    try:
        res = llm.ask(rewrite_prompt(title, h["slug"], before_ctx, h, instruction, op.get("sources") or [], _marks(marks),
                                     _page_context(root, pages)),
                      backend=backend, system=SYSTEM, model="sonnet", run_kw={"wait_s": 600, "poll_every": 10})
    except llm.LLMError as e:
        raise ProposalError(400, str(e)) from None
    if not res.ok:
        raise ProposalError(502, f"the model call failed: {res.error[:200]}")
    reply, after = _parse_rewrite(res.text)
    if after is None:
        raise ProposalError(502, "the model's reply had no new text: try saying it differently")
    if after.strip() == h["after"].strip():
        return {"proposal": service.full(p, root), "reply": reply or "Nothing changed.", "hunk_id": hunk_id,
                "others_changed": [], "unchanged": True}
    if op["kind"] == "edit_page":
        tail = _trailing(h["after"]) or ("\n\n" if h["after"] or h["before"] else "\n")
        mine = [x["id"] for x in rev["hunks"] if x["op_id"] == op["id"]]
        new_op = dict(op, new_text=_splice_edit(base, op["new_text"], mine.index(hunk_id), after.rstrip() + tail))
    else:
        new_op = dict(op, text=after.rstrip() + "\n")
    ops = [{k: v for k, v in (new_op if o["id"] == op["id"] else o).items() if k != "id"} for o in rev["ops"]]
    old_ids = {x["id"] for x in rev["hunks"]} - {hunk_id}
    out = service.revise(pid, ops, note=f"rewrite: {instruction[:200]}", root=root)
    new_ids = [x["id"] for x in out["hunks"]]
    fresh = [x for x in out["hunks"] if x["id"] not in old_ids]
    same_place = [x for x in fresh if x["slug"] == h["slug"] and x["at"] == h["at"]]
    card = (same_place or fresh or [None])[0]
    return {"proposal": out, "reply": reply or "I rewrote it.", "hunk_id": card["id"] if card else None,
            "others_changed": sorted(old_ids - set(new_ids)), "unchanged": False}


def revert(pid, root=None) -> dict:
    """Back to the previous revision's ops, as a new revision (nothing is lost: both stay in the history)."""
    root = _root(root)
    p = store.load(root, pid)
    if p["status"] not in ("open", "stale"):
        raise ProposalError(409, f"proposal is {p['status']}")
    if p["current"] == 0:
        raise ProposalError(409, "this is the first version of the change")
    prev = p["revisions"][p["current"] - 1]
    ops = [{k: v for k, v in o.items() if k != "id"} for o in prev["ops"]]
    return service.revise(pid, ops, note=f"back to revision {prev['n']}", root=root)


# -- split a page where the model suggests -------------------------------------------------------------------------------
def split_prompt(info, hint):
    rows = "\n".join(f"[{b['index']}] ({b['kind']}) {' '.join(b['text'].split())[:240]}"
                     for b in info["blocks"] if b["index"] >= info["first"])
    return (f"Page `{info['slug']}` ({info['title']}) as numbered blocks:\n\n{rows}\n\n"
            + (f"The owner says: {hint}\n\n" if hint else "")
            + "Choose where new pages start so each part is one concept. A cut is the index of the block that "
              f"starts a new page (greater than {info['first']}); the first part stays on this page. Reply as JSON:\n"
              '{"reply": "one sentence: why these parts", "cuts": [7], "titles": ["Title of the page starting at 7"]}')


def _parse_split(raw, info):
    obj = llm.json_object(raw) or {}
    valid = {b["index"] for b in info["blocks"] if b["index"] > info["first"]}
    cuts, titles = [], []
    for c, t in zip(obj.get("cuts") or [], obj.get("titles") or []):
        if isinstance(c, int) and c in valid and c not in cuts and isinstance(t, str) and t.strip():
            cuts.append(c)
            titles.append(" ".join(t.split()))
    order = sorted(range(len(cuts)), key=lambda i: cuts[i])
    return str(obj.get("reply") or "").strip(), [cuts[i] for i in order], [titles[i] for i in order]


def split(slug, hint=None, backend=None, root=None) -> dict:
    """The model picks cuts and titles; the restructure producer makes the proposal. {proposal, reply, cuts, titles}."""
    root = _root(root)
    info = restructure.blocks(slug, root=root)
    try:
        res = llm.ask(split_prompt(info, " ".join(str(hint or "").split())), backend=backend, system=SPLIT_SYSTEM,
                      model="sonnet", run_kw={"wait_s": 600, "poll_every": 10})
    except llm.LLMError as e:
        raise ProposalError(400, str(e)) from None
    if not res.ok:
        raise ProposalError(502, f"the model call failed: {res.error[:200]}")
    reply, cuts, titles = _parse_split(res.text, info)
    if not cuts:
        raise ProposalError(422, "the model found no good place to split this page")
    out = restructure.split(slug, cuts, titles, root=root)
    return {"proposal": out, "reply": reply or f"Split into {len(cuts) + 1} pages.", "cuts": cuts, "titles": titles}


# -- apply what the deck decided -----------------------------------------------------------------------------------------
def apply_batch(items, root=None) -> dict:
    """`items` = [{proposal_id, decisions: [{hunk_id, decision}]}]. Per proposal: record the decisions, then apply
    (some accepted, all decided), reject (all rejected) or leave it waiting (cards left for later).
    Returns {applied: [{id, title, commit, pages}], rejected: [id], waiting: [{id, title, undecided}], failed: [...]}."""
    root = _root(root)
    out = {"applied": [], "rejected": [], "waiting": [], "failed": []}
    for item in items or []:
        pid = str(item.get("proposal_id") or "")
        decisions = [d for d in item.get("decisions") or [] if d.get("decision") in ("accept", "reject")]
        try:
            p = service.decide(pid, decisions, root=root) if decisions else service.get(pid, root=root)
            ids = [h["id"] for h in p["hunks"]]
            mine = {hid: d["decision"] for hid, d in p["decisions"].items() if not d.get("suggested")}
            mine.update({d["hunk_id"]: d["decision"] for d in decisions})
            undecided = [hid for hid in ids if hid not in mine]
            if undecided:
                out["waiting"].append({"id": pid, "title": p["title"], "undecided": len(undecided)})
            elif all(mine[hid] == "reject" for hid in ids):
                service.reject(pid, "rejected in Review", root=root)
                out["rejected"].append(pid)
            else:
                r = service.apply(pid, root=root)
                pages = (store.load(root, pid).get("applied") or {}).get("pages") or []
                out["applied"].append({"id": pid, "title": p["title"], "commit": r["commit"], "pages": pages,
                                       "kb_version": r.get("kb_version")})
        except ProposalError as e:
            out["failed"].append({"id": pid, "status": e.status, "message": str(e), **e.extra})
    return out
