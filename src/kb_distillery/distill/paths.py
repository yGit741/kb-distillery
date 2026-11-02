"""Paths for distill sessions."""
import hashlib
import json
import os
import re
import sys

from kb_distillery.vault.schema import DISTILL_DIR, DISTILLED_THINK_PREFIX, THINK_DIR, WIKI_DIR

from kb_distillery.config.paths import think_path, vault_root
from kb_distillery.vault.schema import is_page_file
ROOT = vault_root()
DISTILL_ROOT = os.path.join(ROOT, DISTILL_DIR)

# A distilled page cites its note as `think:<file>`: think is the shared space beside every knowledge base
# (`kbs/think/`), not a folder of this vault. `think/<file>` is the legacy spelling.
THINK_CITE = f"{THINK_DIR}:"


def resolve_think_path(arg):
    """Resolve a CLI arg (`note`, `note.md`, `think/note.md`, `think:note.md`) to the `think/<file>` key."""
    arg = arg.strip().replace("\\", "/")
    if arg.startswith(THINK_CITE):
        arg = arg[len(THINK_CITE):]
    if arg.startswith(f"{THINK_DIR}/"):
        rel = arg
    else:
        name = arg if arg.endswith(".md") else f"{arg}.md"
        rel = f"{THINK_DIR}/{name}"
    if not rel.startswith(f"{THINK_DIR}/") or ".." in rel:
        raise ValueError(f"think path must be under {THINK_DIR}/")
    return rel


def think_cite(think_rel):
    """`think/note.md` → `think:note.md`, the `source:` a distilled page carries."""
    return THINK_CITE + think_rel[len(THINK_DIR) + 1:] if think_rel.startswith(f"{THINK_DIR}/") else think_rel


def think_abs(think_rel):
    """`think/note.md` → its file in the shared think space."""
    return think_path(think_rel)


def think_basename(think_rel):
    return os.path.basename(think_rel)[:-3] if think_rel.endswith(".md") else os.path.basename(think_rel)


def distilled_slug(think_rel):
    """One naming rule for the skill and `kbd distill` (kb_distillery.distill.fanout.slug_for), so they share one page."""
    from .fanout import slug_for
    return slug_for(think_rel[len(THINK_DIR) + 1:] if think_rel.startswith(f"{THINK_DIR}/") else think_rel)


def distilled_wiki_rel(think_rel):
    return f"{WIKI_DIR}/{distilled_slug(think_rel)}.md"


def session_id(think_rel):
    return hashlib.sha1(think_rel.encode()).hexdigest()[:12]


def session_dir_for_think(think_rel):
    return os.path.join(DISTILL_ROOT, session_id(think_rel))


def session_path_for_think(think_rel):
    return os.path.join(session_dir_for_think(think_rel), "session.json")


def load_session_by_think(think_rel):
    path = session_path_for_think(think_rel)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"no distill session for {think_rel}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_session_by_think(think_rel, data):
    sdir = session_dir_for_think(think_rel)
    os.makedirs(sdir, exist_ok=True)
    with open(session_path_for_think(think_rel), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def wiki_slugs():
    slugs = set()
    base = os.path.join(ROOT, WIKI_DIR)
    if os.path.isdir(base):
        for fn in os.listdir(base):
            if is_page_file(fn) and "excalidraw" not in fn:
                slugs.add(fn[:-3])
    return slugs
