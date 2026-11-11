"""The knowledge library: one local folder the user keeps OKF bundles in (folders and .zip files), for the Add dialog.

The path lives in the per-user config folder (`library.toml`, `path = "..."`), never in a kb. `scan()` lists the bundles
directly inside it (depth 1, plus the folder itself) without linting anything; `resolve()` is the only way a path from
the browser reaches the importer: it must lie inside the library. HTTP-free: failures are `LibraryError`. Lives beside
`import_kb` rather than in `services/`: it reuses `find_bundle_root`, and the layer contract keeps services off `init_kb`.
"""
from __future__ import annotations

import os
import tomllib
import zipfile

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import userdir
from kb_distillery.config.layout import WIKI_DIR
from kb_distillery.import_kb import find_bundle_root
from kb_distillery.lint import okf_check

FILE = "library.toml"


class LibraryError(Exception):
    """A path that is not usable; the message says why."""


def _file() -> str:
    return userdir.path(FILE)


def get_path() -> str | None:
    """The configured library folder, or None when none is set (or the file is unreadable)."""
    try:
        with open(_file(), "rb") as f:
            value = tomllib.load(f).get("path")
    except (OSError, ValueError):
        return None
    return value if isinstance(value, str) and value else None


def set_path(path: str | None) -> str | None:
    """Save (or, for None / empty, clear) the library -> the stored path. A path must be an existing folder."""
    path = (path or "").strip()
    if not path:
        try:
            os.remove(_file())
        except FileNotFoundError:
            pass
        return None
    folder = os.path.realpath(os.path.expanduser(path))
    if not os.path.isabs(os.path.expanduser(path)) or not os.path.isdir(folder):
        raise LibraryError(f"{path} is not an existing folder: give an absolute path")
    os.makedirs(userdir.config_dir(), exist_ok=True)
    escaped = folder.replace("\\", "\\\\").replace('"', '\\"')
    with open(_file(), "w", encoding="utf-8") as f:
        f.write(f'path = "{escaped}"\n')
    return folder


def _has_page(folder: str, deep: bool) -> bool:
    for base, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if any(n.endswith(".md") and not okf_check.is_reserved(n) for n in files):
            return True
        if not deep:
            return False
    return False


def _folder_is_bundle(folder: str, deep: bool) -> bool:
    try:
        return _has_page(find_bundle_root(folder), deep)
    except OSError:
        return False


def _zip_is_bundle(path: str) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return any(n.endswith(".md") and not okf_check.is_reserved(os.path.basename(n))
                       and "__MACOSX" not in n.split("/") for n in z.namelist())
    except (zipfile.BadZipFile, OSError):
        return False


def scan(library: str) -> list[dict]:
    """The bundles in `library` -> [{path, name, kind: "folder"|"zip"}], sorted by name; no lint, nothing read but names."""
    out: list[dict] = []
    root = os.path.realpath(library)
    wiki = os.path.join(root, WIKI_DIR)
    if _has_page(root, deep=False) or (os.path.isdir(wiki) and _has_page(wiki, deep=True)):
        out.append({"path": root, "name": os.path.basename(root) or root, "kind": "folder"})
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for name in names:
        if name.startswith("."):
            continue
        full = os.path.join(root, name)
        if os.path.isdir(full):
            if _folder_is_bundle(full, deep=True):
                out.append({"path": full, "name": name, "kind": "folder"})
        elif name.lower().endswith(".zip") and os.path.isfile(full) and _zip_is_bundle(full):
            out.append({"path": full, "name": name[:-4], "kind": "zip"})
    return out


def imported_sources() -> set[str]:
    """The realpaths recorded as `[import] source` by the knowledge bases on this machine."""
    seen: set[str] = set()
    for root in kbconfig.discover().values():
        try:
            with open(os.path.join(root, kbconfig.CONFIG_NAME), "rb") as f:
                src = tomllib.load(f).get("import", {}).get("source")
        except (OSError, ValueError):
            continue
        if isinstance(src, str) and src:
            seen.add(os.path.realpath(src))
    return seen


def listing() -> dict:
    """What GET /api/kb/library answers: {path, bundles: [{path, name, kind, added}]}."""
    path = get_path()
    if not path or not os.path.isdir(path):
        return {"path": path, "bundles": []}
    done = imported_sources()
    return {"path": path, "bundles": [{**b, "added": os.path.realpath(b["path"]) in done} for b in scan(path)]}


def resolve(path: str) -> str:
    """`path` (a folder or .zip) as a real path when it lies inside the library, else `LibraryError`."""
    library = get_path()
    if not library:
        raise LibraryError("no knowledge library is set: set one in the Add dialog's menu")
    real = os.path.realpath(os.path.expanduser(path))
    lib = os.path.realpath(library)
    if real != lib and not real.startswith(lib + os.sep):
        raise LibraryError("that path is not inside your knowledge library")
    return real
