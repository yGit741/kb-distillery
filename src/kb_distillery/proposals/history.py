"""Page history: the versions of one wiki page from the kb's git log, a compare of two of them, and restore as a proposal.

Read-only on the page. Versions are the commits that touched `wiki/<slug>.md`; `kind` is the op of the kb commit
convention `kb(<op>): …` ("other" for anything else). A compare is diffed by `proposals.diff` (the hunks the review
screen renders, `klass` included); a restore creates a proposal whose `edit_page` op sets the page to that version, or
only the chosen blocks of it, and never writes the page itself.
"""
from __future__ import annotations

import re

from kb_distillery.ops import core as opscore
from kb_distillery.proposals import apply as applier
from kb_distillery.proposals import diff, service
from kb_distillery.proposals.model import ProposalError, check_slug
from kb_distillery.vault import wikiio

WORKING = "working"
_SHA = re.compile(r"^[0-9a-f]{4,40}$")
_KIND = re.compile(r"^kb\(([\w-]+)\):")
_SEP = "\x1f"


def _rel(slug):
    return f"wiki/{check_slug(slug)}.md"


def _root(root):
    return root or service.DEFAULT_ROOT


def history(slug, root=None) -> list[dict]:
    """[{sha, short, date, subject, kind}] newest first."""
    root = _root(root)
    rel = _rel(slug)
    out = opscore._git(root, "log", f"--format=%H{_SEP}%h{_SEP}%aI{_SEP}%s", "--", rel).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split(_SEP)
        if len(parts) != 4:
            continue
        sha, short, date, subject = parts
        m = _KIND.match(subject)
        rows.append({"sha": sha, "short": short, "date": date, "subject": subject, "kind": m.group(1) if m else "other"})
    return rows


def version_text(slug, ref, root=None):
    """The page text at `ref` (a commit sha or "working"); 404 when the sha or the page there does not exist."""
    root = _root(root)
    if ref == WORKING:
        text = applier.read_page(root, slug)
        if text is None:
            raise ProposalError(404, f"page {slug} does not exist in the working tree")
        return text
    if not isinstance(ref, str) or not _SHA.match(ref):
        raise ProposalError(404, f"unknown version {ref!r}")
    proc = opscore._git(root, "show", f"{ref}:{_rel(slug)}")
    if proc.returncode != 0:
        raise ProposalError(404, f"page {slug} has no version {ref}")
    return proc.stdout


def _hunks(slug, old, new):
    op = {"id": "history", "kind": "edit_page", "slug": slug}
    hunks, _ = diff.build({slug: old}, [{**op, "new_text": new}])
    return hunks


def compare(slug, frm, to=WORKING, root=None) -> dict:
    """{from, to, hunks, page}: hunks turn the `from` text into the `to` text; `page` is the `from` text's blocks (the
    shape of a proposal render page) so the review diff components can show the unchanged paragraphs around them."""
    root = _root(root)
    old, new = version_text(slug, frm, root), version_text(slug, to, root)
    hunks = _hunks(slug, old, new)
    return {"from": frm, "to": to, "hunks": hunks, "page": diff.render({slug: old}, hunks)[0]}


def _revert(slug, old, new, hunk_ids):
    """`new` with the blocks of the hunks in `hunk_ids` (compare ids, from `old` to `new`) put back as they were in `old`."""
    ids = [h["id"] for h in _hunks(slug, old, new)]
    ob = diff.split_blocks(wikiio.strip_my_notes(old))
    nb = diff.split_blocks(wikiio.strip_my_notes(wikiio.preserve_my_notes(old, new)))
    parts, k = [], 0
    for tag, i1, i2, j1, j2 in diff._opcodes(ob, nb):
        if tag == "equal":
            parts += [b["raw"] for b in nb[j1:j2]]
            continue
        chosen = ob[i1:i2] if ids[k] in hunk_ids else nb[j1:j2]
        k += 1
        parts += [b["raw"] for b in chosen]
    return wikiio.preserve_my_notes(new, "".join(parts))


def restore(slug, sha, blocks=None, to=WORKING, root=None) -> dict:
    """Create the restore proposal; returns {proposal_id}. Whole version, or only `blocks` (compare hunk ids)."""
    root = _root(root)
    if sha == WORKING:
        raise ProposalError(400, "restore needs a commit sha, not the working page")
    old = version_text(slug, sha, root)
    current = applier.read_page(root, slug)
    if blocks:
        new = version_text(slug, to, root)
        known = {h["id"] for h in _hunks(slug, old, new)}
        unknown = sorted(set(blocks) - known)
        if unknown:
            raise ProposalError(400, f"no such block in this comparison: {', '.join(unknown)}")
        text, what = _revert(slug, old, new, set(blocks)), f"{len(set(blocks))} block(s)"
    else:
        text, what = old, "the whole page"
    short = sha[:7]
    if current is None:
        ops = [{"kind": "create_page", "slug": slug, "text": text, "reason": f"restored from {short}"}]
    else:
        ops = [{"kind": "edit_page", "slug": slug, "new_text": text, "reason": f"restored from {short}"}]
        if wikiio.preserve_my_notes(current, text) == current:
            raise ProposalError(409, "the page already reads like that")
    p = service.create(f"Restore {what} of {slug} from {short}", ops,
                       {"kind": "restore", "instruction": f"restore {slug} from {short}", "context": {"sha": sha, "slug": slug}},
                       root=root)
    return {"proposal_id": p["id"]}
