"""Restructure producers: merge, split and extract. Each builds typed ops and hands them to `service.create` with
producer {kind: restructure, context: {action}}; nothing is written until the owner reviews and applies.

* merge   {slugs, survivor, title?, backend?}: the survivor's text plus the other pages' sections appended under their
  titles (deterministic; with `backend` an LLM pass proposes a tidier body instead), a `tombstone_page` per other page
  (redirect to the survivor) and a `rewrite_link` per page that links to a tombstoned slug.
* split   {slug, cuts, titles}: `cuts` are block indices (the `at` of `diff.render`) where a new piece starts; the
  original keeps the first piece plus a "Continued in" list, every other piece is a `create_page`.
* extract {slug, from_at, to_at, title}: one inclusive block range becomes a new page, a one-line link is left behind.

Every response is the proposal plus `ripple`: [{slug, links}] = the pages whose links to the changed page are
rewritten (merge) or point at the original (split, extract; listed for information). A page's `## My notes` is the
owner's: `edit_page` keeps each page's own section last, so the other pages' notes ride along in a labelled section
of the survivor body and stay on their (tombstoned) page too.
"""
from __future__ import annotations

import os
import re

from kb_distillery import llm
from kb_distillery.proposals import apply as applier
from kb_distillery.proposals import diff, service
from kb_distillery.proposals.model import ProposalError, check_slug
from kb_distillery.vault import frontmatter
from kb_distillery.vault import links as page_links
from kb_distillery.vault import pages as vault_pages
from kb_distillery.vault import schema, wikiio

LIST_KEYS = ("tags", "aliases", "related")
SYSTEM = "You tidy a personal wiki page that was assembled from several pages. Reply with the page body only."
BODY_CHARS = 30000


def _root(root):
    return root or service.DEFAULT_ROOT


def _text(root, slug, field="slug"):
    check_slug(slug, field)
    text = applier.read_page(root, slug)
    if text is None:
        raise ProposalError(404, f"no page {slug!r}")
    return text


def _blocks(text):
    """(blocks of the page without My notes, index of the first content block: after the front matter and the blank
    run that follows it)."""
    blocks = diff.split_blocks(wikiio.strip_my_notes(text))
    first = next((i for i, b in enumerate(blocks) if b["kind"] != diff.FM and b["raw"].strip()), len(blocks))
    return blocks, first


def _count_links(text, target):
    """Prose page links to `target` in `text` (My notes, code, math and comments never count: they are not rewritten)."""
    body = wikiio.split_page(text)[1]
    spans = page_links.protected_spans(body)
    return sum(1 for m in page_links.PAGE_LINK.finditer(body)
               if m.group(2) == target and not any(a <= m.start() < b for a, b in spans))


def _inbound(root, targets, skip=()):
    """{slug: {target: n}} for every page (outside `skip`) with prose links to one of `targets`."""
    out = {}
    for slug, (_rel, _fm, text) in sorted(vault_pages.load_wiki_pages(root).items()):
        if slug in skip:
            continue
        hits = {t: _count_links(text, t) for t in targets}
        hits = {t: n for t, n in hits.items() if n}
        if hits:
            out[slug] = hits
    return out


def _ripple(by_page):
    return [{"slug": s, "links": sum(h.values())} for s, h in sorted(by_page.items())]


def _title(text, slug):
    return page_links.shown_title(page_links.title_of(text, slug)) or slug


def _slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")[:60].strip("-")


def _new_slug(title, page_type, taken, fallback):
    stem = _slugify(title) or fallback
    slug = schema.make_slug(page_type, stem) if page_type else stem
    base, n = slug, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    taken.add(slug)
    return slug


def _create(title, ops, action, instruction, context, root, note=None):
    producer = {"kind": "restructure", "instruction": instruction, "context": dict(context, action=action)}
    p = service.create(title, ops, producer=producer, note=note, root=root)
    return p


def _result(proposal, ripple):
    return dict(proposal, ripple=ripple)


# -- merge ---------------------------------------------------------------------------------------------------------------
def _demote(body):
    """Body with its leading `# ` heading dropped and the other headings one level deeper (fenced code untouched)."""
    out, fenced, dropped = [], False, False
    for line in body.split("\n"):
        if re.match(r"^[ \t]{0,3}(```|~~~)", line):
            fenced = not fenced
        elif not fenced and re.match(r"^#{1,6}[ \t]", line):
            if not dropped and line.startswith("# "):
                dropped = True
                continue
            dropped = True
            if line.startswith("######"):
                out.append(line)
            else:
                out.append("#" + line)
            continue
        out.append(line)
    return "\n".join(out).strip("\n")


def _notes_body(text):
    notes = wikiio.my_notes(text)
    return notes.removeprefix(wikiio.MY_NOTES).strip("\n") if notes else ""


def _union(*lists):
    seen = []
    for lst in lists:
        for v in [lst] if isinstance(lst, str) else lst or []:
            if v and v not in seen:
                seen.append(v)
    return seen


def _set_list(text, key, values):
    """Set `key: [a, b]` in the front matter, replacing a flow or block list in place (appended when missing)."""
    line = f"{key}: [{', '.join(frontmatter.scalar(str(v)) for v in values)}]"

    def fn(inner):
        out, done, skip = [], False, False
        for ln in inner.split("\n"):
            if skip and (ln.startswith((" ", "\t", "- ")) or ln.rstrip() == "-" or not ln.strip()):
                continue
            skip = False
            if re.match(rf"^{re.escape(key)}:", ln):
                out.append(line)
                done, skip = True, True
            else:
                out.append(ln)
        if not done:
            out.append(line)
        return "\n".join(out)
    return wikiio.edit_front_matter(text, fn)


def _merge_frontmatter(text, survivor, others):
    """Survivor wins on scalars; tags, aliases (plus every merged slug) and related are the union, minus the pages
    that are going away."""
    fm = frontmatter.parse(text)[0]
    if fm is None:
        return text
    gone = {s for s, _t in others}
    fms = [fm] + [frontmatter.parse(t)[0] or {} for _s, t in others]
    tags = _union(*(f.get("tags") for f in fms))
    aliases = _union(*(f.get("aliases") for f in fms), sorted(gone))
    related = [s for s in _union(*(page_links.refs(f.get("related")) for f in fms)) if s != survivor and s not in gone]
    for key, vals in (("tags", tags), ("aliases", aliases)):
        if vals:
            text = _set_list(text, key, vals)
    if related:
        text = _set_list(text, "related", [page_links.page_path(s) for s in related])
    return text


def concatenate(survivor, survivor_text, others) -> str:
    """The merged page text. `others` = [(slug, text)]."""
    base = wikiio.strip_my_notes(survivor_text).rstrip("\n")
    parts = [base]
    carried = []
    for slug, text in others:
        body = _demote(wikiio.split_page(wikiio.strip_my_notes(text))[1])
        parts.append(f"## {_title(text, slug)}\n\n{body}" if body else f"## {_title(text, slug)}")
        notes = _notes_body(text)
        if notes:
            carried.append(f"### From {_title(text, slug)}\n\n{notes}")
    if carried:
        parts.append("## Notes carried over\n\n" + "\n\n".join(carried))
    merged = "\n\n".join(parts) + "\n"
    merged = _merge_frontmatter(merged, survivor, others)
    return wikiio.preserve_my_notes(survivor_text, merged)


def _tidy(merged, backend, root):
    """The LLM pass: a tidier body for the merged page; the front matter and My notes stay ours."""
    fm, body = wikiio.split_page(wikiio.strip_my_notes(merged))
    prompt = ("These pages were merged into one by plain concatenation. Rewrite the body as one coherent page: remove "
              "duplicate claims, keep every distinct claim and every link, keep the markdown link form "
              "`[Title](slug.md)`, keep one `# ` title. Do not add facts. Reply with the body only, no front matter.\n\n"
              f"{body[:BODY_CHARS]}")
    try:
        res = llm.ask(prompt, backend=backend, system=SYSTEM, model="sonnet", run_kw={"wait_s": 600, "poll_every": 10})
    except llm.LLMError as e:
        raise ProposalError(400, str(e)) from None
    if not res.ok:
        raise ProposalError(502, f"the model call failed: {res.error[:200]}")
    titles = page_links.read_titles(os.path.join(root, "wiki"))
    new_body = page_links.to_disk(wikiio.strip_my_notes(wikiio.split_page(res.text)[1]).strip("\n"), titles) + "\n"
    if not new_body.strip():
        raise ProposalError(502, "the model returned an empty page")
    return wikiio.preserve_my_notes(merged, fm + "\n" + new_body.lstrip("\n") if fm else new_body)


def _plan_merge(slugs, survivor, root):
    """(slugs, texts, others, merged concatenation) after validating the request."""
    slugs = list(dict.fromkeys(slugs or []))
    if len(slugs) < 2:
        raise ProposalError(400, "merge needs at least two pages")
    if survivor not in slugs:
        raise ProposalError(400, f"survivor {survivor!r} must be one of the merged pages")
    texts = {s: _text(root, s) for s in slugs}
    others = [(s, texts[s]) for s in slugs if s != survivor]
    return slugs, texts, others, concatenate(survivor, texts[survivor], others)


def _merge_links(root, slugs, survivor, others, merged):
    """{slug: {merged slug: n}}: the pages whose links change, the survivor included for links its merged text carries."""
    gone = [s for s, _t in others]
    by_page = _inbound(root, gone, skip=set(slugs))
    own = {g: _count_links(merged, g) for g in gone}
    own = {g: n for g, n in own.items() if n}
    if own:
        by_page[survivor] = own
    return by_page


def merge_preview(slugs, survivor, root=None) -> dict:
    """What a merge would rewrite, without making a proposal: {ripple: [{slug, links}]}."""
    root = _root(root)
    slugs, _texts, others, merged = _plan_merge(slugs, survivor, root)
    return {"ripple": _ripple(_merge_links(root, slugs, survivor, others, merged))}


def merge(slugs, survivor, title=None, backend=None, root=None) -> dict:
    root = _root(root)
    slugs, _texts, others, merged = _plan_merge(slugs, survivor, root)
    by_page = _merge_links(root, slugs, survivor, others, merged)       # counted on the concatenation: the LLM keeps links
    if backend:
        merged = _tidy(merged, backend, root)
    gone = [s for s, _t in others]
    ops = [{"kind": "edit_page", "slug": survivor, "new_text": merged,
            "reason": "merge " + ", ".join(gone) + f" into {survivor}"}]
    ops += [{"kind": "tombstone_page", "slug": s, "redirect_to": survivor,
             "reason": f"merged into {survivor}"} for s in gone]
    for slug, hits in sorted(by_page.items()):
        ops += [{"kind": "rewrite_link", "slug": slug, "from_slug": g, "to_slug": survivor,
                 "reason": f"{g} was merged into {survivor}"} for g in gone if g in hits and
                (slug != survivor or _count_links(merged, g))]
    names = ", ".join(gone)
    proposal = _create(title or f"Merge {names} into {survivor}", ops, "merge",
                       f"Merge {', '.join(slugs)} into {survivor}",
                       {"slugs": slugs, "survivor": survivor, "tidy": bool(backend)}, root)
    return _result(proposal, _ripple(by_page))


def blocks(slug, root=None) -> dict:
    """The blocks the cut view lists: {slug, title, first, blocks: [{index, kind, text}]}. `first` is the first content
    block; a cut or range starts at `first` or later (`diff.render` indexes the same blocks)."""
    root = _root(root)
    text = _text(root, slug)
    bl, first = _blocks(text)
    return {"slug": slug, "title": _title(text, slug), "first": first,
            "blocks": [{"index": i, "kind": b["kind"], "text": b["raw"]} for i, b in enumerate(bl)]}


# -- split ---------------------------------------------------------------------------------------------------------------
def _fm_of(text):
    return wikiio.split_page(text)[0]


def _piece_text(fm_source, title, blocks):
    """A new page: the front matter of `fm_source` (title replaced, aliases dropped) and `blocks` under `# title`."""
    text = fm_source
    fm = frontmatter.parse(fm_source)[0] or {}
    if "title" in fm:
        text = wikiio.set_key(text, "title", frontmatter.quote(title))
    if "aliases" in fm:
        text = wikiio.edit_front_matter(text, lambda inner: re.sub(r"^aliases:[^\n]*\n?(?:[ \t-][^\n]*\n?)*", "", inner + "\n",
                                                                 flags=re.M).rstrip("\n"))
    head = _fm_of(text)
    body = "".join(b["raw"] for b in blocks).strip("\n")
    first = blocks[0]["raw"].lstrip() if blocks else ""
    if first.startswith("# "):
        body = re.sub(r"^# [^\n]*", f"# {title}", body.lstrip(), count=1)
    else:
        body = f"# {title}\n\n{body}"
    return (head + "\n" if head else "") + body + "\n"


def _int(v, field):
    if isinstance(v, bool) or not isinstance(v, int):
        raise ProposalError(400, f"{field} must be a whole number, got {v!r}")
    return v


def split(slug, cuts, titles, root=None) -> dict:
    root = _root(root)
    text = _text(root, slug)
    blocks, first = _blocks(text)
    cuts = [_int(c, "cuts") for c in cuts or []]
    titles = [" ".join(str(t or "").split()) for t in titles or []]
    if not cuts:
        raise ProposalError(400, "give at least one cut")
    if len(titles) != len(cuts) or not all(titles):
        raise ProposalError(400, f"give one non-empty title for each of the {len(cuts)} new pages")
    if len(set(t.lower() for t in titles)) != len(titles):
        raise ProposalError(400, "the titles of the new pages must differ")
    if cuts != sorted(set(cuts)):
        raise ProposalError(400, "cuts must be increasing block indices, each used once")
    if cuts[0] <= first or cuts[-1] >= len(blocks):
        raise ProposalError(400, f"cuts must fall between blocks {first + 1} and {len(blocks) - 1} of {slug}")
    fm = frontmatter.parse(text)[0] or {}
    taken = set(vault_pages.load_wiki_pages(root)) | {slug}
    bounds = [first, *cuts, len(blocks)]
    pieces = [blocks[a:b] for a, b in zip(bounds, bounds[1:])]
    new_slugs = [_new_slug(t, fm.get("type"), taken, f"{slug}-part") for t in titles]
    ops = [{"kind": "create_page", "slug": s, "text": _piece_text(_fm_of(text), t, p),
            "reason": f"split from {slug}"} for s, t, p in zip(new_slugs, titles, pieces[1:])]
    kept = "".join(b["raw"] for b in blocks[:first]) + "".join(b["raw"] for b in pieces[0]).rstrip("\n")
    cont = "\n".join(f"- {page_links.link(s, t)}" for s, t in zip(new_slugs, titles))
    ops.append({"kind": "edit_page", "slug": slug,
                "new_text": wikiio.preserve_my_notes(text, f"{kept}\n\n## Continued in\n\n{cont}\n"),
                "reason": f"{len(titles)} part(s) moved to their own pages"})
    ripple = _ripple(_inbound(root, [slug], skip={slug}))
    proposal = _create(f"Split {slug} into {len(pieces)} pages", ops, "split",
                       f"Split {slug} at blocks {', '.join(map(str, cuts))}",
                       {"slug": slug, "cuts": cuts, "titles": titles, "new_slugs": new_slugs}, root)
    return _result(proposal, ripple)


# -- extract -------------------------------------------------------------------------------------------------------------
def extract(slug, from_at, to_at, title, root=None) -> dict:
    root = _root(root)
    text = _text(root, slug)
    blocks, first = _blocks(text)
    a, b = _int(from_at, "from_at"), _int(to_at, "to_at")
    title = " ".join(str(title or "").split())
    if not title:
        raise ProposalError(400, "title is required")
    if not (first <= a <= b < len(blocks)):
        raise ProposalError(400, f"the range must satisfy {first} <= from_at <= to_at < {len(blocks)}")
    fm = frontmatter.parse(text)[0] or {}
    new_slug = _new_slug(title, fm.get("type"), set(vault_pages.load_wiki_pages(root)) | {slug}, f"{slug}-extract")
    moved = blocks[a:b + 1]
    left = f"{page_links.link(new_slug, title)}\n\n"
    new_blocks = blocks[:a] + [{"kind": "prose", "raw": left}] + blocks[b + 1:]
    new_text = wikiio.preserve_my_notes(text, "".join(x["raw"] for x in new_blocks).rstrip("\n") + "\n")
    ops = [{"kind": "create_page", "slug": new_slug, "text": _piece_text(_fm_of(text), title, moved),
            "reason": f"extracted from {slug}"},
           {"kind": "edit_page", "slug": slug, "new_text": new_text,
            "reason": f"blocks {a}-{b} moved to {new_slug}"}]
    ripple = _ripple(_inbound(root, [slug], skip={slug}))
    proposal = _create(f"Extract {title} from {slug}", ops, "extract", f"Extract blocks {a}-{b} of {slug} as {title}",
                       {"slug": slug, "from_at": a, "to_at": b, "title": title, "new_slug": new_slug}, root)
    return _result(proposal, ripple)
