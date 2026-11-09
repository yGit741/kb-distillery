"""Chat on a page: the owner's message (+ selected spans and @mentioned pages) becomes a proposal, never a direct write.

One model call returns a JSON list of edits {before, after, reason, sources}; each `before` must occur verbatim in the
page body above `## My notes` (that section is the owner's and is never edited). The found ones are applied to the page
text as one `edit_page` op and handed to `service.create` with producer {kind: chat}. A `before` that is not found, or
that lies in My notes, is skipped with a warning. The thread (messages + proposal ids) is stored in
`<kb>/.local/chat/<slug>.json`.
"""
from __future__ import annotations

import difflib
import json
import os
import re

from kb_distillery import llm
from kb_distillery.proposals import apply as applier
from kb_distillery.proposals import service
from kb_distillery.proposals.model import ProposalError, now
from kb_distillery.vault import links
from kb_distillery.vault import pages as vault_pages

MY_NOTES = "## My notes"
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MENTION_CHARS = 2000
PAGE_CHARS = 20000
SYSTEM = ("You edit one page of a personal wiki on the owner's request. Reply with one JSON object and nothing else.")


def _root(root):
    return root or service.DEFAULT_ROOT


def _split(text):
    """(editable part, My notes part): the second starts at `## My notes` or is empty."""
    i = text.find("\n" + MY_NOTES)
    return (text, "") if i < 0 else (text[:i + 1], text[i + 1:])


def _thread_path(root, slug):
    return os.path.join(root, ".local", "chat", f"{slug}.json")


def thread(slug, root=None) -> dict:
    root = _root(root)
    if applier.read_page(root, slug) is None:
        raise ProposalError(404, f"no page {slug!r}")
    try:
        with open(_thread_path(root, slug), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return {"slug": slug, "messages": data.get("messages") or []}


def _append(root, slug, msgs):
    t = thread(slug, root)
    t["messages"] += msgs
    path = _thread_path(root, slug)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"messages": t["messages"]}, f, indent=1)
    os.replace(tmp, path)


def build_prompt(slug, text, message, selections, mentioned) -> str:
    editable, notes = _split(text)
    sel = "\n".join(f"- (block {s.get('block_at')}) \"{s.get('text', '')}\"" for s in selections) or "(none)"
    ctx = "\n\n".join(f"[page: {m}]\n{body[:MENTION_CHARS]}" for m, body in mentioned.items()) or "(none)"
    mine = (f"\n\nThe owner's own section (UNTOUCHABLE, never quote it in `before`, never edit it):\n{notes}"
            if notes else "")
    return (f"Page `{slug}`:\n\n{editable[:PAGE_CHARS]}{mine}\n\n"
            f"Selected spans the owner points at:\n{sel}\n\n"
            f"Pages the owner mentioned (first {MENTION_CHARS} characters each):\n\n{ctx}\n\n"
            f"The owner asks: {message}\n\n"
            "Propose the smallest edits that do it. Each `before` is an exact, unique substring of the page above "
            "(not of the owner's section); `after` replaces it. Reply as JSON:\n"
            '{"reply": "one or two calm sentences to the owner", "edits": [{"before": "...", "after": "...", '
            '"reason": "short", "sources": ["mentioned-slug"]}]}\n'
            'Use "edits": [] when no change is warranted.')


def parse(raw: str) -> tuple[str, list[dict]]:
    obj = llm.json_object(raw)
    if obj is None:
        try:
            arr = json.loads(raw)
        except (TypeError, ValueError):
            arr = None
        obj = {"edits": arr} if isinstance(arr, list) else {}
    rows = obj.get("edits")
    edits = [{"before": str(r.get("before") or ""), "after": str(r.get("after") or ""),
              "reason": str(r.get("reason") or ""),
              "sources": [str(s) for s in r.get("sources") or [] if isinstance(s, str)]}
             for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    return str(obj.get("reply") or "").strip(), edits


def apply_edits(text: str, edits: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """(new text, applied edits, skipped [{before, reason}]); only the part above `## My notes` changes."""
    editable, notes = _split(text)
    applied, skipped = [], []
    for e in edits:
        b = e["before"]
        if not b.strip():
            skipped.append({"before": b, "reason": "empty before"})
        elif b in editable:
            editable = editable.replace(b, e["after"], 1)
            applied.append(e)
        elif notes and b in notes:
            skipped.append({"before": b, "reason": "in My notes, which is never edited"})
        else:
            skipped.append({"before": b, "reason": "text not found on the page"})
    return editable + notes, applied, skipped


def mentions(q: str, root=None, limit=8) -> list[dict]:
    """Pages for the @ picker: slug/title prefix first, then fuzzy matches."""
    root = _root(root)
    pages = vault_pages.load_wiki_pages(root)
    q = (q or "").strip().lower()
    rows = [(s, links.title_of(t, s)) for s, (_r, _fm, t) in pages.items()]
    if not q:
        return [{"slug": s, "title": t} for s, t in sorted(rows)[:limit]]
    scored = []
    for s, t in rows:
        if s.lower().startswith(q) or t.lower().startswith(q):
            score = 2.0
        elif q in s.lower() or q in t.lower():
            score = 1.5
        else:
            score = max(difflib.SequenceMatcher(None, q, s.lower()).ratio(),
                        difflib.SequenceMatcher(None, q, t.lower()).ratio())
            if score < 0.5:
                continue
        scored.append((-score, s, t))
    return [{"slug": s, "title": t} for _sc, s, t in sorted(scored)[:limit]]


def chat(slug, message, selections=None, mention_slugs=None, backend=None, root=None) -> dict:
    root = _root(root)
    text = applier.read_page(root, slug)
    if text is None:
        raise ProposalError(404, f"no page {slug!r}")
    message = str(message or "").strip()
    if not message:
        raise ProposalError(400, "message is required")
    selections = [s for s in selections or [] if isinstance(s, dict)]
    mentioned, unknown = {}, []
    for m in dict.fromkeys(mention_slugs or []):
        body = applier.read_page(root, m) if isinstance(m, str) and SLUG.match(m) and ".." not in m else None
        if body is None:
            unknown.append(m)
        else:
            mentioned[m] = _split(links.body_of(body))[0].strip()
    try:
        res = llm.ask(build_prompt(slug, text, message, selections, mentioned), backend=backend, system=SYSTEM,
                      model="sonnet", run_kw={"wait_s": 600, "poll_every": 10})
    except llm.LLMError as e:
        raise ProposalError(400, str(e)) from None
    if not res.ok:
        raise ProposalError(502, f"the model call failed: {res.error[:200]}")
    reply, edits = parse(res.text)
    new_text, applied, skipped = apply_edits(text, edits)
    proposal_id, hunks = None, 0
    if applied and new_text != text:
        sources = sorted({s for e in applied for s in e["sources"]})
        reason = "; ".join(e["reason"] for e in applied if e["reason"])[:500]
        p = service.create(f"Chat: {message[:60]}", [{"kind": "edit_page", "slug": slug, "new_text": new_text,
                                                      "reason": reason, "sources": sources}],
                           producer={"kind": "chat", "instruction": message,
                                     "context": {"message": message, "mentions": list(mentioned),
                                                 "selections": selections}},
                           root=root, backend=backend)
        proposal_id, hunks = p["id"], len(p["hunks"])
    if not reply:
        reply = "I proposed an edit." if proposal_id else "I found nothing to change."
    out = {"reply": reply, "proposal_id": proposal_id, "hunks": hunks, "skipped": skipped,
           "unknown_mentions": unknown}
    stamp = now()
    _append(root, slug, [{"role": "user", "text": message, "at": stamp, "selections": selections,
                          "mentions": list(mention_slugs or [])},
                         {"role": "assistant", "text": reply, "at": stamp, "proposal_id": proposal_id,
                          "hunks": hunks, "skipped": skipped, "unknown_mentions": unknown}])
    return out
