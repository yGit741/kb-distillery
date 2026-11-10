"""Hunks and composition: the core cuts a revision into reviewable hunks and composes the accepted ones back into pages.

A page is diffed as blocks: the frontmatter is one block, the body (without `## My notes`, which is the user's and never
part of a proposal) is split into paragraphs, headings and list groups. difflib aligns the old and new block lists; each
changed run is one hunk. A hunk id is a hash of its content, so the same change keeps its id (and its decision) across
revisions and recomputations. Composition starts from the base page text, takes the new blocks only where the hunk is
accepted, applies the semantic ops (set_frontmatter, rewrite_link) on top and restores `## My notes`.
"""
from __future__ import annotations

import difflib
import hashlib
import re

from kb_distillery.proposals import trust
from kb_distillery.proposals.model import NOT_YET, ProposalError
from kb_distillery.vault import links as page_links
from kb_distillery.vault import wikiio

_BLOCK = re.compile(
    r"(?:^#{1,6}[ \t][^\n]*(?:\n|$)"                                  # a heading line on its own
    r"|(?:^(?!#{1,6}[ \t])[^\n]*\S[^\n]*(?:\n|$))+)"                    # or a run of non-blank lines
    r"(?:^[ \t]*\n)*", re.M)                                          # plus the blank lines after it
_TOKEN = re.compile(r"\s+|\w+|[^\w\s]")
FM = "fm"


def split_blocks(text: str) -> list[dict]:
    """[{kind: fm|heading|prose, raw}] covering `text` byte for byte (My notes must be stripped by the caller)."""
    fm, body = wikiio.split_page(text)
    out = [{"kind": FM, "raw": fm}] if fm else []
    pos = 0
    for m in _BLOCK.finditer(body):
        gap = body[pos:m.start()]
        if gap:
            if out and out[-1]["kind"] != FM:
                out[-1]["raw"] += gap
            else:
                out.append({"kind": "prose", "raw": gap})
        raw = m.group(0)
        out.append({"kind": "heading" if raw.lstrip().startswith("#") else "prose", "raw": raw})
        pos = m.end()
    if body[pos:]:
        if out and out[-1]["kind"] != FM:
            out[-1]["raw"] += body[pos:]
        else:
            out.append({"kind": "prose", "raw": body[pos:]})
    return out


def word_tokens(before: str, after: str) -> list[list[str]]:
    """Word-level diff as [[op, text]], op in equal|insert|delete, consecutive same ops merged."""
    a, b = _TOKEN.findall(before), _TOKEN.findall(after)
    out: list[list[str]] = []

    def add(op, toks):
        text = "".join(toks)
        if not text:
            return
        if out and out[-1][0] == op:
            out[-1][1] += text
        else:
            out.append([op, text])

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            add("equal", a[i1:i2])
        else:
            add("delete", a[i1:i2])
            add("insert", b[j1:j2])
    return out


def _links(text):
    return set(page_links.targets(text or ""))


def _hunk(slug, op, before, after, structural, at=0, span=0):
    added, removed = sorted(_links(after) - _links(before)), sorted(_links(before) - _links(after))
    h = {"id": "", "op_id": op["id"], "op": op["kind"], "slug": slug,
         "kind": "structure" if structural or added or removed else "prose",
         "before": before, "after": after, "tokens": word_tokens(before, after),
         "reason": op.get("reason", ""), "sources": op.get("sources", []),
         "links_added": added, "links_removed": removed, "at": at, "span": span}
    h["klass"] = trust.classify_hunk(h)
    return h


def _key(block):
    return block["raw"].strip()


def _opcodes(old_blocks, new_blocks):
    sm = difflib.SequenceMatcher(None, [_key(b) for b in old_blocks], [_key(b) for b in new_blocks], autojunk=False)
    return [oc for oc in sm.get_opcodes()]


def _edit_hunks(slug, op, old_text, new_text):
    old_blocks = split_blocks(wikiio.strip_my_notes(old_text))
    new_blocks = split_blocks(wikiio.strip_my_notes(new_text))
    hunks = []
    for tag, i1, i2, j1, j2 in _opcodes(old_blocks, new_blocks):
        if tag == "equal":
            continue
        involved = old_blocks[i1:i2] + new_blocks[j1:j2]
        structural = any(b["kind"] in (FM, "heading") for b in involved)
        before = "".join(b["raw"] for b in old_blocks[i1:i2])
        after = "".join(b["raw"] for b in new_blocks[j1:j2])
        hunks.append(_hunk(slug, op, before, after, structural, at=i1, span=i2 - i1))
    return hunks


def _compose_edit(old_text, new_text, accepted_hunk_ids, hunk_ids):
    """Old text with only the accepted block replacements, `## My notes` of the old text kept."""
    old_blocks = split_blocks(wikiio.strip_my_notes(old_text))
    new_blocks = split_blocks(wikiio.strip_my_notes(new_text))
    parts, k = [], 0
    for tag, i1, i2, j1, j2 in _opcodes(old_blocks, new_blocks):
        if tag == "equal":
            parts += [b["raw"] for b in old_blocks[i1:i2]]
            continue
        hid = hunk_ids[k]
        k += 1
        chosen = new_blocks[j1:j2] if hid in accepted_hunk_ids else old_blocks[i1:i2]
        parts += [b["raw"] for b in chosen]
    return wikiio.preserve_my_notes(old_text, "".join(parts))


def _fm_line(text, key):
    fm, _ = wikiio.split_page(text)
    m = re.search(rf"^{re.escape(key)}:[^\n]*$", fm, re.M)
    return m.group(0) if m else ""


def _set_frontmatter(text, key, value):
    try:
        return wikiio.set_key(text, key, value)
    except wikiio.BodyChanged as e:
        raise ProposalError(400, f"set_frontmatter {key}: {e}") from None


def _rewrite_links(text, from_slug, to_slug):
    """`text` with every prose page link to `from_slug` pointing at `to_slug` (My notes, code and math untouched);
    returns (new text, [(old line, new line)])."""
    fm, body = wikiio.split_page(text)
    spans = page_links.protected_spans(body)
    out, pos, changed = [], 0, []
    for m in page_links.PAGE_LINK.finditer(body):
        if m.group(2) != from_slug or any(a <= m.start() < b for a, b in spans):
            continue
        anchor = f"#{m.group(3)}" if m.group(3) else ""
        out += [body[pos:m.start()], f"[{m.group(1)}]({page_links.page_path(to_slug)}{anchor})"]
        pos = m.end()
        changed.append(m.start())
    new_body = "".join(out) + body[pos:]
    lines_old, lines_new = body.split("\n"), new_body.split("\n")
    pairs = [(o, n) for o, n in zip(lines_old, lines_new) if o != n]
    return fm + new_body, pairs


def tombstone_text(text, redirect_to, title=None):
    """The page `text` turned into a tombstone: its front matter plus `redirect_to: <slug>.md`, a one-line body that
    links the new home, and its `## My notes` (the owner's text is never dropped)."""
    shown = page_links.shown_title(title or "") or redirect_to
    mine = wikiio.my_notes(text)
    fm = wikiio.split_page(wikiio.set_key(text, "redirect_to", page_links.page_path(redirect_to)))[0] \
        if wikiio.split_page(text)[0] else ""
    heading = page_links.title_of(text, "")
    out = f"{fm}\n# {heading}\n\nThis page moved to {page_links.link(redirect_to, shown)}.\n" if heading else \
        f"{fm}\nThis page moved to {page_links.link(redirect_to, shown)}.\n"
    return out + ("\n" + mine if mine else "")


def _uniq(hunks):
    seen = {}
    for h in hunks:
        base = hashlib.sha1(f"{h['slug']}|{h['op']}|{h['before']}|{h['after']}".encode()).hexdigest()[:10]
        n = seen.get(base, 0)
        seen[base] = n + 1
        h["id"] = base if n == 0 else f"{base}-{n}"
    return hunks


def _title(work, slug):
    text = work.get(slug)
    return page_links.title_of(text, slug) if text else slug


def _order(ops):
    """Page-writing ops first (create/edit), then the semantic ones, each group in op order."""
    first = [o for o in ops if o["kind"] in ("create_page", "edit_page")]
    return first + [o for o in ops if o not in first]


def _check_once(ops):
    seen = set()
    for o in ops:
        if o["kind"] in ("create_page", "edit_page", "tombstone_page"):
            if o["slug"] in seen:
                raise ProposalError(400, f"page {o['slug']} is created, edited or tombstoned twice in one revision")
            seen.add(o["slug"])


def build(base_texts: dict, ops: list[dict]) -> tuple[list[dict], dict]:
    """(hunks, {slug: text with every hunk accepted}) for a revision. `base_texts` = {slug: page text or None}."""
    _check_once(ops)
    work = dict(base_texts)
    hunks = []
    for op in _order(ops):
        kind, slug = op["kind"], op.get("slug")
        if kind == "edit_page":
            if work.get(slug) is None:
                raise ProposalError(400, f"edit_page: no page {slug} (use create_page)")
            new = wikiio.preserve_my_notes(work[slug], op["new_text"])
            hunks += _edit_hunks(slug, op, work[slug], new)
            work[slug] = new
        elif kind == "create_page":
            if work.get(slug) is not None:
                raise ProposalError(400, f"create_page: page {slug} exists (use edit_page)")
            hunks.append(_hunk(slug, op, "", op["text"], True))
            work[slug] = op["text"]
        elif kind == "set_frontmatter":
            if work.get(slug) is None:
                raise ProposalError(400, f"set_frontmatter: no page {slug}")
            before = _fm_line(work[slug], op["key"])
            work[slug] = _set_frontmatter(work[slug], op["key"], op["value"])
            hunks.append(_hunk(slug, op, before, f"{op['key']}: {op['value']}", True))
        elif kind == "rewrite_link":
            if work.get(slug) is None:
                raise ProposalError(400, f"rewrite_link: no page {slug}")
            work[slug], pairs = _rewrite_links(work[slug], op["from_slug"], op["to_slug"])
            if not pairs:
                raise ProposalError(400, f"rewrite_link: {slug} has no prose link to {op['from_slug']}")
            hunks.append(_hunk(slug, op, "\n".join(p[0] for p in pairs), "\n".join(p[1] for p in pairs), True))
        elif kind == "tombstone_page":
            if work.get(slug) is None:
                raise ProposalError(400, f"tombstone_page: no page {slug}")
            hunks.append(_hunk(slug, op, work[slug], f"tombstone {slug} -> {op['redirect_to']}", True))
            work[slug] = tombstone_text(work[slug], op["redirect_to"], _title(work, op["redirect_to"]))
        elif kind == "move_block":
            hunks.append(_hunk(op["from_slug"], op, "", f"move block {op['block_id']} -> {op['to_slug']}", True))
    return _uniq(hunks), work


def compose(base_texts: dict, ops: list[dict], hunks: list[dict], accepted: set[str]) -> dict:
    """{slug: new page text} for the pages the accepted hunks change. `base_texts` must equal the pages on disk."""
    by_op: dict[str, list[dict]] = {}
    for h in hunks:
        by_op.setdefault(h["op_id"], []).append(h)
    work = dict(base_texts)
    for op in _order(ops):
        mine = by_op.get(op["id"], [])
        if not any(h["id"] in accepted for h in mine):
            continue
        kind, slug = op["kind"], op.get("slug")
        if kind in NOT_YET:
            raise ProposalError(501, f"{kind} is validated but not applied yet (a later proposals item implements it); "
                                     f"reject its hunk to apply the rest")
        if kind == "edit_page":
            new = wikiio.preserve_my_notes(work[slug], op["new_text"])
            work[slug] = _compose_edit(work[slug], new, accepted, [h["id"] for h in mine])
        elif kind == "create_page":
            work[slug] = op["text"]
        elif kind == "set_frontmatter":
            work[slug] = _set_frontmatter(work[slug], op["key"], op["value"])
        elif kind == "rewrite_link":
            work[slug] = _rewrite_links(work[slug], op["from_slug"], op["to_slug"])[0]
        elif kind == "tombstone_page":
            work[slug] = tombstone_text(work[slug], op["redirect_to"], _title(work, op["redirect_to"]))
    return {s: t for s, t in work.items() if t is not None and t != base_texts.get(s)}


def render(base_texts: dict, hunks: list[dict]) -> list[dict]:
    """Per touched page: its text, its blocks (index + raw) and where each hunk sits (block index `at`, `span` blocks)."""
    out = []
    for slug, text in base_texts.items():
        blocks = split_blocks(wikiio.strip_my_notes(text)) if text is not None else []
        out.append({"slug": slug, "exists": text is not None, "text": text or "",
                    "blocks": [{"index": i, "kind": b["kind"], "text": b["raw"]} for i, b in enumerate(blocks)],
                    "my_notes": wikiio.my_notes(text or ""),
                    "hunks": [{"id": h["id"], "kind": h["kind"], "op": h["op"], "at": h["at"], "span": h["span"]}
                              for h in hunks if h["slug"] == slug]})
    return out
