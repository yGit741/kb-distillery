"""Tier-1 checks: cheap, deterministic, no model. They run on every new revision, before anyone sees it.

(a) every link target in the new text resolves to a page, or to a page the same proposal creates;
(b) structural lint of the resulting pages (kb_distillery.lint.lint's own checks, run on an in-memory page set:
    the kb's pages with the proposal's results overlaid; the real tree is never written);
(c) the privacy ratchet terms (kb_distillery.lint.privacy) on the new text;
(d) the frontmatter still parses.
A finding is {severity, code, message, slug, hunk_id?, source}. An `error` blocks apply unless its hunk is rejected.
"""
from __future__ import annotations

import contextlib
import re
import threading

from kb_distillery.lint import lint as vault_lint
from kb_distillery.lint import privacy
from kb_distillery.vault import frontmatter, wikiio
from kb_distillery.vault import pages as vault_pages


def finding(severity, code, message, slug, hunk_id=None, source="tier1"):
    out = {"severity": severity, "code": code, "message": message, "slug": slug, "source": source}
    if hunk_id:
        out["hunk_id"] = hunk_id
    return out


def _hunk_for(hunks, slug, needle):
    """The first hunk of `slug` whose new text contains `needle` (else the page's first hunk, else None)."""
    mine = [h for h in hunks if h["slug"] == slug]
    for h in mine:
        if needle and needle in h["after"]:
            return h["id"]
    return mine[0]["id"] if mine else None


_LINT_LOCK = threading.Lock()          # lint.lint keeps its findings in module lists


@contextlib.contextmanager
def _captured():
    """Run lint.lint checks and keep only the messages they add; its module lists are restored afterwards."""
    with _LINT_LOCK:
        yield from _capture_locked()


def _capture_locked():
    ne, nw = len(vault_lint.errors), len(vault_lint.warnings)
    got = {"errors": [], "warnings": []}
    try:
        yield got
    finally:
        got["errors"] = vault_lint.errors[ne:]
        got["warnings"] = vault_lint.warnings[nw:]
        del vault_lint.errors[ne:]
        del vault_lint.warnings[nw:]


_QUOTED_LINK = re.compile(r"(\[[^\n]*?\]\([^)\s]+\))")


def tier1(root: str, hunks: list[dict], results: dict) -> list[dict]:
    """Findings for a revision whose every-hunk-accepted page texts are `results` ({slug: text})."""
    out: list[dict] = []
    changed = {s: t for s, t in results.items() if t is not None}
    pages = vault_pages.load_wiki_pages(root)
    for slug, text in changed.items():
        fm = frontmatter.parse(text)[0]
        if fm is None:                                                         # (d)
            out.append(finding("error", "frontmatter", "the page has no parsable frontmatter block", slug,
                               _hunk_for(hunks, slug, "---")))
            pages.pop(slug, None)
            continue
        pages[slug] = (f"wiki/{slug}.md", fm, text)
    lintable = {s: pages[s] for s in changed if s in pages}
    # (a) + (b): lint's link check on the overlaid page set; it only reads `pages` (created pages are in it).
    with _captured() as got:
        if lintable:
            vault_lint.check_links(_scoped(pages, lintable))
            vault_lint.check_table_pipes(lintable)
    for sev, msgs in (("error", got["errors"]), ("warning", got["warnings"])):
        for msg in msgs:
            rel, _, text = msg.partition(": ")
            slug = rel.removeprefix("wiki/").removesuffix(".md")
            if slug not in lintable:
                continue
            m = _QUOTED_LINK.search(text)
            code = "link" if "link" in text else "lint"
            out.append(finding(sev, code, text, slug, _hunk_for(hunks, slug, m.group(1) if m else "")))
    for slug, text in changed.items():                                        # (b) the reserved section
        for msg in wikiio.check_my_notes(text):
            out.append(finding("error", "my-notes", msg, slug, None))
    personal = privacy.personal_pattern()                                      # (c) only the new text
    for h in hunks:
        added = "".join(t for op, t in h["tokens"] if op == "insert") if h["before"] else h["after"]
        for line in added.split("\n"):
            if line.strip() and privacy.matches(line, personal):
                out.append(finding("error", "privacy", "new text carries a personal term or a secret (privacy ratchet)",
                                   h["slug"], h["id"]))
                break
    return out


def _scoped(pages, lintable):
    """check_links walks every page it is given; give it all pages for resolution but only report the touched ones."""
    class Scoped(dict):
        def items(self):                    # iterate only the pages under review
            return lintable.items()
    return Scoped(pages)


def blocking(findings: list[dict], decisions: dict) -> list[dict]:
    """The error findings that still block apply: those on no hunk, or on a hunk not rejected."""
    return [f for f in findings if f["severity"] == "error"
            and not (f.get("hunk_id") and decisions.get(f["hunk_id"], {}).get("decision") == "reject")]
