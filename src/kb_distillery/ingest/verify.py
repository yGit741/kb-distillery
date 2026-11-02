"""Pre-ingest checks: corpus disposition, paper naming, file on disk."""
import os
import re
import sys

from kb_distillery.lint.lint import read_manifest, parse_frontmatter, walk
from kb_distillery.core.schema import PAPER_NAME, PAPER_YEAR_MAX, PAPER_YEAR_MIN, WIKI_DIR
from .paths import ROOT
from kb_distillery.core.schema import is_page_file


def corpus_disposition(raw_rel):
    rows = read_manifest()
    if raw_rel not in rows:
        raise ValueError(f"{raw_rel} not in corpus manifest — run src/kb_distillery/lint/lint.py first")
    return rows[raw_rel]["disposition"]


def existing_digest_for_raw(raw_rel, pages=None):
    """Return wiki rel if a page already cites this raw file. With `pages` (a book part),
    only a page whose `section_pages:` is exactly that range counts."""
    for rel in walk(WIKI_DIR, ".md"):
        if not is_page_file(os.path.basename(rel)):
            continue
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        fm = parse_frontmatter(text)
        if not fm or str(fm.get("raw") or "") != raw_rel:
            continue
        if pages is None:
            return rel
        m = re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*", str(fm.get("section_pages") or ""))
        if m and (int(m.group(1)), int(m.group(2))) == tuple(pages):
            return rel
    return None


def verify_raw(raw_rel):
    raw_rel = raw_rel.replace(os.sep, "/").lstrip("./")
    path = os.path.join(ROOT, raw_rel)
    if not os.path.isfile(path):
        raise ValueError(f"file not found: {raw_rel}")
    disp = corpus_disposition(raw_rel)
    if disp not in ("queued", "source", "partial"):
        raise ValueError(f"{raw_rel} disposition is {disp!r} — only queued/source/partial "
                         "can be ingested")
    name = os.path.basename(raw_rel)
    if raw_rel.startswith("raw/printed-docs/") and re.match(PAPER_NAME, name):
        year = int(name[:4])
        if not (PAPER_YEAR_MIN <= year <= PAPER_YEAR_MAX):
            raise ValueError(f"implausible year {year} in {name}")
    return raw_rel
