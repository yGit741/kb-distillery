"""Vault paths for ingest sessions."""
import hashlib
import json
import os
import sys

from kb_distillery.lint.lint import parse_frontmatter
from kb_distillery.vault.schema import INGEST_DIR, MANIFEST, MANIFEST_COLS, ROOT_MD, WIKI_DIR, is_page_file

from kb_distillery.paths import vault_root
ROOT = vault_root()  # KB_ROOT: share build
INGEST_ROOT = os.path.join(ROOT, INGEST_DIR)

PERSON_SLUGS = frozenset({"nadav-cohen", "gal-vardi", "daniel-soudry", "amit-daniely"})


def _page_type(slug):
    path = os.path.join(ROOT, WIKI_DIR, f"{slug}.md")
    try:
        with open(path, encoding="utf-8") as f:
            return (parse_frontmatter(f.read()) or {}).get("type")
    except OSError:
        return None


def collection_of(raw_rel):
    """Slugs in corpus.tsv `collection` for a raw file (hubs and people it belongs to)."""
    path = os.path.join(ROOT, MANIFEST)
    if not raw_rel or not os.path.isfile(path):
        return []
    col = MANIFEST_COLS.index("collection")
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if parts[0] == raw_rel and len(parts) > col:
                return [c.strip() for c in parts[col].split(",") if c.strip()]
    return []


def set_collection(raw_rel, slugs):
    """Add slugs to a raw file's corpus.tsv `collection`, seeding the row if lint hasn't seen the
    file yet (lint fills sha1/kind/disposition on its next run and keeps the collection)."""
    slugs = [s for s in slugs if s]
    if not slugs:
        return
    path = os.path.join(ROOT, MANIFEST)
    lines = open(path, encoding="utf-8").read().split("\n") if os.path.isfile(path) else []
    col = MANIFEST_COLS.index("collection")
    for i, line in enumerate(lines):
        parts = line.split("\t")
        if parts[0] == raw_rel:
            parts += [""] * (len(MANIFEST_COLS) - len(parts))
            have = [c for c in parts[col].split(",") if c]
            parts[col] = ",".join(dict.fromkeys(have + slugs))
            lines[i] = "\t".join(parts)
            break
    else:
        row = dict.fromkeys(MANIFEST_COLS, "")
        row.update(path=raw_rel, disposition="queued", collection=",".join(slugs))
        if lines and lines[-1] == "":
            lines.pop()
        lines += ["\t".join(row[c] for c in MANIFEST_COLS), ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def person_from_raw(raw_rel):
    """Bibliography owner: the first person page named in the file's corpus.tsv `collection`."""
    if not raw_rel or raw_rel == "none":
        return None
    for slug in collection_of(raw_rel.replace(os.sep, "/")):
        if slug in PERSON_SLUGS or _page_type(slug) == "person":
            return slug
    return None


def sha1_file(rel):
    h = hashlib.sha1()
    with open(os.path.join(ROOT, rel), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def session_dir(sha):
    return os.path.join(INGEST_ROOT, sha)


def session_path(sha):
    return os.path.join(session_dir(sha), "session.json")


def load_session(sha):
    path = session_path(sha)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"no session at {INGEST_DIR}/{sha}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_session(sha, data):
    d = session_dir(sha)
    os.makedirs(d, exist_ok=True)
    with open(session_path(sha), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def page_title(slug):
    """The title the app shows for wiki/<slug>.md (what a link to it reads as); the slug when the page is missing."""
    from kb_distillery.vault import links
    return links.read_title(os.path.join(ROOT, WIKI_DIR), slug)


def wiki_titles():
    """{slug: title the app shows} of every wiki page (what a link to it reads as); a mapping, so it also serves as the
    set of known slugs."""
    from kb_distillery.vault import links
    return links.read_titles(os.path.join(ROOT, WIKI_DIR))


def wiki_slugs():
    slugs = set()
    base = os.path.join(ROOT, WIKI_DIR)
    for fn in os.listdir(base):
        if is_page_file(fn) and "excalidraw" not in fn:
            slugs.add(fn[:-3])
    think_base = os.path.join(base, "think")
    if os.path.isdir(think_base):
        for fn in os.listdir(think_base):
            if fn.endswith(".md"):
                slugs.add(fn[:-3])
    return slugs

def resolve_wikilink_slug(name, known):
    """Map area/concept name to an existing wiki slug (a bare theme name → its theme- page)."""
    if not name:
        return None
    if name in known:
        return name
    theme = name if name.startswith("theme-") else f"theme-{name}"
    if theme in known:
        return theme
    return None

