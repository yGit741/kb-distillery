"""`ops favorite add|remove|list`: the one writer of meta/favorites.json, and the guard every page-removing step calls.

Each add/remove changes the file and commits it as one knowledge step (`kb(refine): favorite add <slug> (kb-x.y.z)`)
through `core.commit_op`, so it is linted, versioned, logged and pushed like any other step; nothing here runs a raw VCS
command. Both refuse while an ops session is open (409) and put the file back as it was when the step fails.
Each returns `{ok, sha, version, slugs}` (+ `reason` when it was a no-op: `already` / `absent`).

The guard (`guard`, `apply_to_step`) is called by `core.commit_op` for every knowledge step: a favorite page that the
step deletes (a merge, a split that drops the original, a delete, a rename away) is refused unless `confirm` is given;
a confirmed delete drops the slug from the favorites in the same step, and a rename moves the mark to the new slug.
"""
from __future__ import annotations

import os

from kb_distillery.git import commit_policy as cp
from kb_distillery.ops import core
from kb_distillery.vault import favorites as fv
from kb_distillery.vault.favorites import FavoritesError
from kb_distillery.vault.schema import WIKI_DIR, is_page_file

OP = "refine"
RENAME_SIMILARITY = 0.5            # share of a deleted page's lines found again in a new page: that is a rename


# ---------- the guard ----------

def _slug_of(path):
    """The page slug of a wiki page path, or None for any other path."""
    if path.startswith(WIKI_DIR.rstrip("/") + "/") and path.endswith(".md") and is_page_file(os.path.basename(path)):
        return os.path.basename(path)[:-3]
    return None


def guard(root, targets, confirm=False, verb="delete"):
    """Raise `core.OpsError` when any slug in `targets` is a favorite and `confirm` is not given. Returns the favorites hit."""
    hit = sorted(set(targets) & set(fv.load(root)))
    if hit and not confirm:
        raise core.OpsError("; ".join(f"{s} is a favorite: pass --confirm-favorite to {verb} it" for s in hit))
    return hit


def _head_text(root, path):
    proc = core._git(root, "show", f"HEAD:{path}")
    return proc.stdout if proc.returncode == 0 else None


def _similarity(a, b):
    la, lb = {x.strip() for x in a.splitlines() if x.strip()}, {x.strip() for x in b.splitlines() if x.strip()}
    return len(la & lb) / len(la) if la else 0.0


def _renames(root, gone, new):
    """{old slug: new slug} for each deleted page whose content (mostly) reappears in a new page; one-to-one, best first."""
    pairs = []
    for old in gone:
        old_text = _head_text(root, old)
        if old_text is None:
            continue
        for path in new:
            try:
                with open(os.path.join(root, path), encoding="utf-8") as f:
                    score = _similarity(old_text, f.read())
            except OSError:
                continue
            if score >= RENAME_SIMILARITY:
                pairs.append((score, old, path))
    out, used = {}, set()
    for _, old, path in sorted(pairs, reverse=True):
        if _slug_of(old) not in out and path not in used:
            out[_slug_of(old)] = _slug_of(path)
            used.add(path)
    return out


def apply_to_step(root, paths, confirm=False):
    """Called by `core.commit_op` with the paths one knowledge step will commit. Finds the wiki pages it deletes or renames,
    refuses when one is a favorite and `confirm` is not given, and rewrites meta/favorites.json (rename: the new slug is a
    favorite; confirmed delete: the slug is dropped). Returns the extra paths to commit ([] when the file did not change)."""
    favs = fv.load(root)
    if not favs:
        return []
    gone = [p for p in paths if _slug_of(p) in favs and not os.path.exists(os.path.join(root, p))]
    if not gone:
        return []
    # a page that moved folders keeps its slug: only a slug that no page has any more is gone
    still = fv.page_slugs(root)
    gone = [p for p in gone if _slug_of(p) not in still]
    if not gone:
        return []
    new = [p for p in paths if _slug_of(p) and os.path.exists(os.path.join(root, p)) and _head_text(root, p) is None]
    moved = _renames(root, gone, new)
    removed = [_slug_of(p) for p in gone if _slug_of(p) not in moved]
    guard(root, removed, confirm)
    after = [moved.get(s, s) for s in favs if s not in removed]
    if sorted(set(after)) == favs:
        return []
    fv.write(root, after)
    return [fv.FAVORITES_REL]


# ---------- add / remove / list ----------

def _head(root):
    return core._git(root, "rev-parse", "-q", "--verify", "HEAD").stdout.strip()


def _undo_attempt(root, before, head):
    """A step that did not land: unstage the file and put it back as it was (a step that DID land is left alone)."""
    if _head(root) != head:
        return
    core._git(root, "reset", "-q", "--", fv.FAVORITES_REL)
    fv.write_text(root, before)


def _step(root, slug, summary, before, slugs, lint, push):
    head = _head(root)
    try:
        sha = core.commit_op(OP, slug, summary, paths=[fv.FAVORITES_REL], lint=lint, root=root, push=push, _locked=True)
    except core.OpsError as e:
        _undo_attempt(root, before, head)
        raise FavoritesError(409, "knowledge step refused: " + str(e)) from e
    except Exception as e:  # noqa: BLE001 - any failure leaves the working tree as it was
        if _head(root) == head:
            _undo_attempt(root, before, head)
            raise FavoritesError(500, "knowledge step failed: " + str(e)) from e
        sha = _head(root)
    if not sha:
        _undo_attempt(root, before, head)
        raise FavoritesError(409, "the change was not committed (the file is owned by another open session); nothing changed")
    version = cp.last_version(root)
    return {"ok": True, "sha": sha, "version": ("kb-" + cp.fmt_version(version)) if version else None, "slugs": slugs}


def _change(root, slug, add, lint, push):
    try:
        with core.ops_lock(root):
            s = core.current_session(root)
            if s:
                raise FavoritesError(409, "an ops session is open (" + s["op"] + " " + s["target"] + ") - finish it first")
            before = fv.read_text(root)
            slugs = fv.parse(before)
            if add and slug in slugs:
                return {"ok": False, "reason": "already", "sha": None, "version": None, "slugs": slugs}
            if not add and slug not in slugs:
                return {"ok": False, "reason": "absent", "sha": None, "version": None, "slugs": slugs}
            if add and slug not in fv.page_slugs(root):
                raise FavoritesError(404, f"{slug!r} is not a wiki page; only a page can be a favorite")
            new = sorted(set(slugs) | {slug}) if add else [s for s in slugs if s != slug]
            fv.write(root, new)
            return _step(root, slug, f"favorite {'add' if add else 'remove'} {slug}", before, new, lint, push)
    except core.OpsError as e:
        raise FavoritesError(409, str(e)) from e


def add(slug, root=core.ROOT, lint=True, push=True):
    return _change(root, fv.clean_slug(slug), True, lint, push)


def remove(slug, root=core.ROOT, lint=True, push=True):
    return _change(root, fv.clean_slug(slug), False, lint, push)


def list_slugs(root=core.ROOT):
    return fv.load(root)
