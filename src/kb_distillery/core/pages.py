"""Read a vault's wiki pages and corpus manifest from disk, with no lint dependency.

The linter (`kb_distillery.lint.lint`) wraps these with its own `ROOT`; core modules (scopes, coherence)
call them directly, so core never imports lint.
"""

import os

from kb_distillery.core import frontmatter
from kb_distillery.core.schema import MANIFEST, MANIFEST_COLS, WIKI_DIR, is_page_file


def parse_frontmatter(text):
    """Flat `key: value`, `key: [a, b]`, plus the OKF shapes (kb_distillery.core.frontmatter). None without a block."""
    return frontmatter.parse(text)[0]


def walk(root, d, ext=None):
    """Sorted root-relative paths of the non-hidden files under `root/d` (optionally ending in `ext`)."""
    out = []
    base = os.path.join(root, d)
    if not os.path.isdir(base):
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [x for x in dirnames if not x.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            if ext and not fn.endswith(ext):
                continue
            out.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))
    return sorted(out)


def wiki_page_files(root):
    """Repo-relative paths of the wiki's markdown pages: the OKF reserved files (index.md, log.md) are not pages."""
    return [rel for rel in walk(root, WIKI_DIR, ".md") if is_page_file(os.path.basename(rel))]


def load_wiki_pages(root):
    """{slug: (rel, frontmatter, text)} without schema validation."""
    pages = {}
    for rel in wiki_page_files(root):
        if "excalidraw" in rel:
            continue
        text = open(os.path.join(root, rel), encoding="utf-8").read()
        slug = os.path.basename(rel)[:-3]
        fm = parse_frontmatter(text)
        if fm:
            pages[slug] = (rel, fm, text)
    return pages


def read_manifest(root):
    """{path: row dict} from `root/meta/corpus.tsv`; {} when it is missing."""
    path = os.path.join(root, MANIFEST)
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or line.startswith("path\t"):
                continue
            parts = line.split("\t")
            parts += [""] * (len(MANIFEST_COLS) - len(parts))
            rows[parts[0]] = dict(zip(MANIFEST_COLS, parts[:len(MANIFEST_COLS)]))
    return rows
