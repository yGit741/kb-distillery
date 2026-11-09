"""Flags: the owner marks a span of a page as inaccurate with a short note, keeps reading, and later asks for one
proposal that addresses every open flag. Flags live in `<kb>/.local/flags/<slug>.json` as
[{id, block_at, text, note, created, resolved_by}]; a flag is resolved by the proposal "Fix all flagged" made.

The fix is one model call (through `kb_distillery.llm`) listing every open flag with the paragraph around it; the answer
is a list of edits {before, after, reason} applied by the helper chat shares (`proposals.edits`), so the `## My notes`
section is never edited. A flag whose span is no longer on the page is `orphaned` (reported, never sent to the model).
"""
from __future__ import annotations

import json
import os
import re
import uuid

from kb_distillery import llm
from kb_distillery.proposals import apply as applier
from kb_distillery.proposals import service
from kb_distillery.proposals.chat import PAGE_CHARS, SLUG, parse
from kb_distillery.proposals.edits import apply_edits, split
from kb_distillery.proposals.model import ProposalError, now

TEXT_MAX = 2000
NOTE_MAX = 500
SYSTEM = "You fix inaccuracies flagged by the owner of a personal wiki. Reply with one JSON object and nothing else."


def _root(root):
    return root or service.DEFAULT_ROOT


def _path(root, slug):
    return os.path.join(root, ".local", "flags", f"{slug}.json")


def _page(root, slug) -> str:
    text = applier.read_page(root, slug) if SLUG.match(slug or "") and ".." not in slug else None
    if text is None:
        raise ProposalError(404, f"no page {slug!r}")
    return text


def _load(root, slug) -> list[dict]:
    try:
        with open(_path(root, slug), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict) and r.get("id")] if isinstance(data, list) else []


def _save(root, slug, rows):
    path = _path(root, slug)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    os.replace(tmp, path)


_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _plain(s: str) -> str:
    """What the owner sees: links reduced to their label, emphasis marks dropped, white space collapsed."""
    return " ".join(_LINK.sub(r"\1", s).replace("*", "").replace("_", "").replace("`", "").split())


def _on_page(text: str, editable: str) -> bool:
    """The flagged span is still on the page: as written, or as rendered (the owner selects rendered text)."""
    return bool(text) and (text in editable or " ".join(text.replace("_", "").split()) in _plain(editable))


def _view(row, editable) -> dict:
    return {"id": row["id"], "block_at": row.get("block_at"), "text": row.get("text", ""), "note": row.get("note", ""),
            "created": row.get("created", ""), "resolved_by": row.get("resolved_by"),
            "orphaned": row.get("resolved_by") is None and not _on_page(row.get("text", ""), editable)}


def list_flags(slug, root=None) -> list[dict]:
    root = _root(root)
    editable = split(_page(root, slug))[0]
    return [_view(r, editable) for r in _load(root, slug)]


def count(slug, root=None) -> dict:
    rows = list_flags(slug, root)
    open_ = [r for r in rows if r["resolved_by"] is None]
    return {"open": len(open_), "orphaned": sum(1 for r in open_ if r["orphaned"])}


def add(slug, text, note="", block_at=None, root=None) -> dict:
    root = _root(root)
    editable = split(_page(root, slug))[0]
    text = str(text or "").strip()
    if not text:
        raise ProposalError(400, "text is required")
    if len(text) > TEXT_MAX or len(str(note or "")) > NOTE_MAX:
        raise ProposalError(400, f"text is at most {TEXT_MAX} characters and the note at most {NOTE_MAX}")
    row = {"id": uuid.uuid4().hex[:8], "block_at": block_at if isinstance(block_at, int) else None, "text": text,
           "note": str(note or "").strip(), "created": now(), "resolved_by": None}
    _save(root, slug, _load(root, slug) + [row])
    return _view(row, editable)


def remove(slug, flag_id, root=None) -> None:
    root = _root(root)
    _page(root, slug)
    rows = _load(root, slug)
    kept = [r for r in rows if r["id"] != flag_id]
    if len(kept) == len(rows):
        raise ProposalError(404, f"no flag {flag_id!r} on {slug!r}")
    _save(root, slug, kept)


def _around(editable, text) -> str:
    """The paragraph that holds the span."""
    for para in editable.split("\n\n"):
        if text in para or " ".join(text.split()) in _plain(para):
            return para.strip()
    return text


def build_prompt(slug, text, flags) -> str:
    editable, notes = split(text)
    items = "\n\n".join(f"Flag {i + 1}\n  span: \"{f['text']}\"\n  owner's note: {f['note'] or '(none)'}\n"
                        f"  paragraph: {_around(editable, f['text'])}" for i, f in enumerate(flags))
    mine = (f"\n\nThe owner's own section (UNTOUCHABLE, never quote it in `before`, never edit it):\n{notes}"
            if notes else "")
    return (f"Page `{slug}`:\n\n{editable[:PAGE_CHARS]}{mine}\n\n"
            f"The owner marked these spans as inaccurate while reading:\n\n{items}\n\n"
            "Propose the smallest edits that address every flag. Each `before` is an exact, unique substring of the "
            "page above (not of the owner's section); `after` replaces it. Reply as JSON:\n"
            '{"reply": "one or two calm sentences to the owner", "edits": [{"before": "...", "after": "...", '
            '"reason": "short"}]}\n'
            'Use "edits": [] when a flag needs no change.')


def fix(slug, backend=None, root=None) -> dict:
    root = _root(root)
    text = _page(root, slug)
    rows = _load(root, slug)
    editable = split(text)[0]
    open_ = [r for r in rows if r.get("resolved_by") is None]
    usable = [r for r in open_ if _on_page(r.get("text", ""), editable)]
    orphaned = [r["id"] for r in open_ if r not in usable]
    if not usable:
        raise ProposalError(400, "no open flag to fix" if not open_ else "every open flag is orphaned: its text is no longer on the page")
    try:
        res = llm.ask(build_prompt(slug, text, usable), backend=backend, system=SYSTEM, model="sonnet",
                      run_kw={"wait_s": 600, "poll_every": 10})
    except llm.LLMError as e:
        raise ProposalError(400, str(e)) from None
    if not res.ok:
        raise ProposalError(502, f"the model call failed: {res.error[:200]}")
    reply, edits = parse(res.text)
    new_text, applied, skipped = apply_edits(text, edits)
    out = {"reply": reply, "proposal_id": None, "hunks": 0, "flag_ids": [r["id"] for r in usable],
           "orphaned": orphaned, "skipped": skipped}
    if applied and new_text != text:
        reason = "; ".join(e["reason"] for e in applied if e["reason"])[:500]
        p = service.create(f"Fix {len(usable)} flagged passage{'s' if len(usable) != 1 else ''} in {slug}",
                           [{"kind": "edit_page", "slug": slug, "new_text": new_text, "reason": reason, "sources": []}],
                           producer={"kind": "flags", "instruction": "; ".join(r["note"] for r in usable if r["note"]),
                                     "context": {"flag_ids": out["flag_ids"], "slug": slug}},
                           root=root, backend=backend)
        out["proposal_id"], out["hunks"] = p["id"], len(p["hunks"])
        ids = set(out["flag_ids"])
        _save(root, slug, [dict(r, resolved_by=p["id"]) if r["id"] in ids else r for r in rows])
    else:
        out["flag_ids"] = []  # nothing was proposed, so nothing is resolved
    if not out["reply"]:
        out["reply"] = "I proposed an edit." if out["proposal_id"] else "I found nothing to change."
    return out
