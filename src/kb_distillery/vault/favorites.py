"""Favorites: a binary mark on a wiki page, kept at the kb level in `meta/favorites.json`.

The file is committed knowledge: `{"v": 1, "slugs": ["learning-theory", ...]}` with the slugs sorted and unique. A
favorite is a page slug (the file name without `.md`), nothing else; the page itself carries no field, so this is not a
schema matter. Only `ops favorite` writes the file (`kb_distillery.ops.favorite`), so every change lands as one
knowledge step; the knowledge operations that delete a page keep it in step (the guard in the same module).

Pure file logic: no HTTP, no commits. Every function takes the kb root explicitly.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile

from kb_distillery.vault import pages

FAVORITES_REL = "meta/favorites.json"
VERSION = 1
MAX_SLUG = 128
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,%d}$" % (MAX_SLUG - 1))


class FavoritesError(Exception):
    """A refusal with an HTTP-ish status (400 invalid, 404 unknown, 405 read-only, 409 conflict) and a plain message."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def clean_slug(slug):
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise FavoritesError(400, f"a favorite is a page slug (letters, digits, dots, dashes; at most {MAX_SLUG}), got {slug!r}")
    return slug


def page_slugs(root):
    """The slugs of the wiki's pages (file name without `.md`)."""
    return {os.path.basename(rel)[:-3] for rel in pages.wiki_page_files(root)}


def read_text(root):
    """The file's text, or None when the kb has no favorites yet."""
    try:
        with open(os.path.join(root, FAVORITES_REL), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def parse(text):
    """The sorted slugs in `text` (None or blank = none). A damaged file is a 409: the owner fixes or removes it."""
    if text is None or not text.strip():
        return []
    try:
        data = json.loads(text)
    except ValueError:
        raise FavoritesError(409, f"{FAVORITES_REL} is not valid JSON; fix or remove it") from None
    if not isinstance(data, dict) or not isinstance(data.get("slugs"), list):
        raise FavoritesError(409, f'{FAVORITES_REL} must be {{"v": {VERSION}, "slugs": [...]}}')
    try:
        return sorted({clean_slug(s) for s in data["slugs"]})
    except FavoritesError as e:
        raise FavoritesError(409, f"{FAVORITES_REL}: {e}") from None


def load(root):
    return parse(read_text(root))


def render(slugs):
    """Deterministic file text: two-space indent, sorted unique slugs, trailing newline."""
    return json.dumps({"v": VERSION, "slugs": sorted(set(slugs))}, indent=2, ensure_ascii=False) + "\n"


def write_text(root, text):
    """Write `text` to meta/favorites.json (None removes the file). Atomic; the caller commits."""
    full = os.path.join(root, FAVORITES_REL)
    if text is None:
        with contextlib.suppress(FileNotFoundError):
            os.remove(full)
        return
    os.makedirs(os.path.dirname(full), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(full), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, full)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def write(root, slugs):
    """Write the list (an empty list removes the file)."""
    write_text(root, render(slugs) if slugs else None)
