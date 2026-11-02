"""Shared backlog helpers for ingest CLI and dashboard."""
import os

from .paths import ROOT
from kb_distillery.core.schema import is_page_file


def is_shallow_paper(text: str) -> bool:
    """True if a paper (or book part) page lacks a real ## Key equations block."""
    if "type: paper" not in text and "type: part" not in text:
        return False
    if "## Key equations" not in text:
        return True
    block = text.split("## Key equations", 1)[1].split("##", 1)[0].strip()
    return not block or block == "—" or len(block) <= 5


def shallow_paper_slugs(wiki_dir=None):
    """Return slugs of paper pages flagged for deeper digest."""
    base = wiki_dir or os.path.join(ROOT, "wiki")
    shallow = []
    if not os.path.isdir(base):          # a vault with no wiki/ yet (e.g. an early content commit)
        return shallow
    for fn in os.listdir(base):
        if not is_page_file(fn) or fn.startswith(("q-", "theme-")):
            continue
        text = open(os.path.join(base, fn), encoding="utf-8").read()
        if is_shallow_paper(text):
            shallow.append(fn[:-3])
    return sorted(shallow)
