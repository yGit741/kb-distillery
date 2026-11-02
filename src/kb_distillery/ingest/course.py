"""Course/series hubs during ingest: find a row, tick it on finalize, add rows on catalog.

The hub page's `## Contents` table is the truth (src/kb_distillery/core/hubs.py); corpus.tsv `collection` must
agree with it, so every write here goes through both.
"""
import os

from .paths import ROOT, collection_of, page_title, set_collection
from kb_distillery.lint.lint import parse_frontmatter
from kb_distillery.core.schema import CONTENTS_COLLECTIONS
from kb_distillery.core import hubs
from kb_distillery.core import wikiio


def _hub_path(slug):
    return os.path.join(ROOT, "wiki", f"{slug}.md")


def load_hub(slug):
    """(text, rows) of a course/series page; raises ValueError if it isn't one."""
    path = _hub_path(slug)
    if not os.path.isfile(path):
        raise ValueError(f"no wiki page {slug!r}")
    text = open(path, encoding="utf-8").read()
    if (parse_frontmatter(text) or {}).get("type") not in CONTENTS_COLLECTIONS:
        raise ValueError(f"{slug} is not a course/series hub")
    return text, hubs.parse_contents(text)


def _save(slug, text, rows):
    text = wikiio.edit_body(text, lambda t: hubs.replace_contents(t, rows))
    text = _set_status(text, hubs.hub_status(rows))
    wikiio.write_page(_hub_path(slug), text)


def _set_status(text, status):
    return wikiio.set_key(text, "maturity", status)      # front matter only, never a body line


def resolve_row(slug, n):
    """`--row N` (1-based, as printed in the Contents table) → the row dict."""
    _text, rows = load_hub(slug)
    try:
        row = rows[int(str(n).lstrip("#")) - 1]
    except (ValueError, IndexError):
        raise ValueError(f"no row {n!r} in {slug} — rows run 1–{len(rows)}")
    if row["status"] == hubs.SKIP:
        raise ValueError(f"row {n} ({row['title']}) is marked skip — set its Status to — first")
    return row


def hub_row_for_raw(raw_rel):
    """(hub slug, 1-based row number, row) for the first course/series table listing this file."""
    for slug in collection_of(raw_rel):
        try:
            _text, rows = load_hub(slug)
        except ValueError:
            continue
        i, row = hubs.find_row(rows, raw_rel)
        if row is not None:
            return slug, i + 1, row
    return None, None, None


def record_row(slug, raws, page_slug, status):
    """Tick the row holding these files as digested by page `page_slug`."""
    text, rows = load_hub(slug)
    i, _row = hubs.find_row(rows, raws[0])
    if i is None:
        rows = hubs.add_row(rows, page_slug, raws)
        set_collection(raws[0], [slug])
        i = len(rows) - 1
    _save(slug, text, hubs.tick(rows, i, status, page_slug, page_title(page_slug)))
    return f"wiki/{slug}.md"


def add_member(slug, raw_rel, title):
    """Catalog: list a new file on its hub and record the membership in corpus.tsv."""
    text, rows = load_hub(slug)
    _save(slug, text, hubs.add_row(rows, title, [raw_rel]))
    set_collection(raw_rel, [slug])
