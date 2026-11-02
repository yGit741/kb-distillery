"""Migration-time file handling: snapshot, restore and throwaway copies of a kb (used by `ops/migrate.py`; the
migrations package is where raw-aware file code lives). Not a migration: the name has no number."""
import filecmp
import os
import shutil

# What a migration may rewrite is the kb's own text; these are never copied, snapshotted or restored.
_SKIP = {"raw", ".git", ".cache", "_quarantine", "node_modules", ".ops", "__pycache__"}


def _tree(root):
    """Relative paths of every file under `root` outside _SKIP (symlinks as files)."""
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        for fn in files:
            yield os.path.relpath(os.path.join(dirpath, fn), root)


def _snapshot(root, dest):
    for rel in _tree(root):
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(root, rel), target, follow_symlinks=False)


def _restore(root, snap):
    """Put `root` back exactly as `snap` was taken: changed files rewritten, new files removed, deleted ones recreated."""
    before = set(_tree(snap))
    for rel in set(_tree(root)) - before:
        os.remove(os.path.join(root, rel))
    for rel in before:
        cur, old = os.path.join(root, rel), os.path.join(snap, rel)
        if os.path.islink(old) or not os.path.exists(cur) or not filecmp.cmp(cur, old, shallow=False):
            os.makedirs(os.path.dirname(cur), exist_ok=True)
            if os.path.lexists(cur):
                os.remove(cur)
            shutil.copy2(old, cur, follow_symlinks=False)


def link_bulk(root, copy):
    """Link the user's source files into a throwaway copy (never copied, never written)."""
    src = os.path.join(root, "raw")
    if os.path.isdir(src):
        os.symlink(os.path.realpath(src), os.path.join(copy, "raw"))
