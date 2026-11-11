"""Add sources to a kb from the app, with no model call: files land in raw/inbox/ and are catalogued as `distill ingest` does.

HTTP-free (`kb_distillery.server.routers.inbox_add` relays `SourceError(status, message)`). Each call is one knowledge step
(`kb(catalog): add N sources from the app`) through `ops.core.commit_op`; nothing here runs a raw VCS command.

  add_files(files)    [(name, bytes)] -> one result per file: added | duplicate | refused
  link_folder(path)   take the supported files of a folder on this machine through the same path (a second link of the same
                      folder finds every file already present, so it adds nothing and commits nothing)

A file is refused when catalog has no format for its extension. A file is a duplicate when its sha1 (the 12 hex characters
`meta/corpus.tsv` stores) is already in the corpus, in raw/inbox/, or earlier in the same batch. Files are written through the
kb's storage connector, so they follow the kb's `[storage]` choice and raw stays immutable.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import re

from kb_distillery.config.paths import vault_root
from kb_distillery.git import commit_policy as cp
from kb_distillery.ingest import catalog
from kb_distillery.ops import core
from kb_distillery.storage import StorageError, for_kb
from kb_distillery.vault.schema import MANIFEST, MANIFEST_COLS

DEFAULT_ROOT = vault_root()
ACCEPTED = frozenset({".pdf", *catalog.SLIDE_EXTS, *catalog.WEB_EXTS, *catalog.IMAGE_EXTS})
INBOX = "raw/inbox/"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_FOLDER_FILES = 500
MAX_FOLDER_BYTES = 512 * 1024 * 1024
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class SourceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def clean_name(name: str) -> str:
    """The inbox spelling of a file name: its base name, spaces and odd characters as `-`, no leading dot, extension lower-cased."""
    base = os.path.basename((name or "").replace("\\", "/"))
    stem, ext = os.path.splitext(base)
    stem = _UNSAFE.sub("-", stem).strip("-.") or "untitled"
    return stem + _UNSAFE.sub("", ext).lower()


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def _corpus(root: str):
    """(sha1s, basenames) of every row in meta/corpus.tsv."""
    shas, names = set(), set()
    path = os.path.join(root, MANIFEST)
    if os.path.isfile(path):
        col = MANIFEST_COLS.index("sha1")
        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if parts[0] == "path":
                    continue
                names.add(os.path.basename(parts[0]))
                if len(parts) > col and parts[col]:
                    shas.add(parts[col])
    return shas, names


def _free_name(name: str, taken: set) -> str:
    stem, ext = os.path.splitext(name)
    candidate, n = name, 1
    while candidate in taken:
        n += 1
        candidate = f"{stem}-{n}{ext}"
    return candidate


def _step(root: str, items, summary_fn, collection: str = "", year: int | None = None):
    """Save `items` ([(name, bytes)]) into raw/inbox/, catalog them, commit once. Returns (results, sha | None).
    With a `year`, a file whose content already waits in raw/inbox/ (stored earlier, not catalogued) is filed from there."""
    try:
        store = for_kb(root=root)
    except StorageError as e:
        raise SourceError(409, str(e)) from None
    try:
        lock = core.ops_lock(root)
        with lock:
            session = core.current_session(root)
            if session:
                raise SourceError(409, f"an ops session is open ({session['op']} {session['target']}) - finish it first")
            before = core.knowledge_state(root)
            shas, names = _corpus(root)
            inbox_keys = list(store.list(INBOX))
            names |= {os.path.basename(k) for k in inbox_keys}
            waiting = {}                                        # sha1 -> key of a file stored in the inbox, not catalogued
            for k in inbox_keys:
                try:
                    waiting[store.info(k).sha1[:12]] = k
                except StorageError:
                    pass
            results, added = [], []
            for raw_name, data in items:
                name = clean_name(raw_name)
                shown = raw_name or name
                ext = os.path.splitext(name)[1]
                if ext not in ACCEPTED:
                    results.append({"name": shown, "status": "refused",
                                    "reason": f"unsupported file type {ext or '(none)'}: use one of {', '.join(sorted(ACCEPTED))}"})
                elif not data:
                    results.append({"name": shown, "status": "refused", "reason": "the file is empty"})
                elif len(data) > MAX_FILE_BYTES:
                    results.append({"name": shown, "status": "refused", "reason": f"larger than {MAX_FILE_BYTES >> 20} MB"})
                elif _sha(data) in shas:
                    results.append({"name": shown, "status": "duplicate", "reason": "the same content is already in this knowledge base"})
                elif _sha(data) in waiting and year and waiting[_sha(data)].startswith(INBOX):
                    key = waiting.pop(_sha(data))               # the year it was waiting for: file the stored copy
                    shas.add(_sha(data))
                    added.append((key[len(INBOX):], len(results)))
                    results.append({"name": shown, "status": "added", "raw_path": key})
                elif _sha(data) in waiting:
                    results.append({"name": shown, "status": "duplicate", "reason": "the same content is already in this knowledge base"})
                else:
                    name = _free_name(name, names)
                    store.put(INBOX + name, data)
                    shas.add(_sha(data))
                    names.add(name)
                    added.append((name, len(results)))
                    results.append({"name": shown, "status": "added", "raw_path": INBOX + name})
            if not added:
                return results, None
            _catalog(added, results, collection, year)
            sha = core.commit_op("catalog", "app-upload", summary_fn(len(added)), paths=core.changed_since(before, root),
                                 root=root, _locked=True)
            return results, sha
    except core.OpsError as e:
        raise SourceError(409, "knowledge step refused: " + str(e)) from e


def _catalog(added, results, collection, year=None):
    """Catalog each new inbox file as `drain_inbox` does (one lint at the end, by the commit). A file catalog cannot place stays
    in raw/inbox/ and says why."""
    was = catalog._LINT_DEFERRED
    catalog._LINT_DEFERRED = True
    try:
        for name, i in added:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    dest, _slug = catalog.catalog(INBOX + name, collection=collection, year=year)
                results[i]["raw_path"] = dest
            except (ValueError, NotImplementedError, OSError) as e:
                results[i]["reason"] = f"stored in raw/inbox/ but not catalogued yet: {e}"
    finally:
        catalog._LINT_DEFERRED = was


def _result(sha, root):
    version = cp.last_version(root) if sha else None
    return {"commit": sha, "version": ("kb-" + cp.fmt_version(version)) if version else None}


def add_files(files, root: str | None = None, collection: str = "", year: int | None = None) -> dict:
    root = root or DEFAULT_ROOT
    results, sha = _step(root, files, lambda n: f"add {n} source{'s' if n != 1 else ''} from the app", collection, year)
    return {"files": results, **_result(sha, root)}


def _inside(a: str, b: str) -> bool:
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:
        return False


def link_folder(path: str, root: str | None = None) -> dict:
    root = os.path.realpath(root or DEFAULT_ROOT)
    if not isinstance(path, str) or not os.path.isabs(path):
        raise SourceError(422, "the folder must be an absolute path")
    folder = os.path.realpath(path)
    if not os.path.isdir(folder):
        raise SourceError(422, f"{path} is not an existing folder")
    if _inside(folder, root):
        raise SourceError(422, "that folder is inside this knowledge base; its files are already part of it")
    if _inside(root, folder):
        raise SourceError(422, "that folder contains this knowledge base; pick a folder of sources")
    items, skipped, total = [], 0, 0
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            if fn.startswith(".") or os.path.islink(full) or os.path.splitext(fn)[1].lower() not in ACCEPTED:
                skipped += 1
                continue
            size = os.path.getsize(full)
            if size == 0 or size > MAX_FILE_BYTES:
                skipped += 1
                continue
            total += size
            if len(items) >= MAX_FOLDER_FILES or total > MAX_FOLDER_BYTES:
                raise SourceError(413, f"that folder has more than {MAX_FOLDER_FILES} files or {MAX_FOLDER_BYTES >> 20} MB of sources; link a smaller one")
            items.append(full)
    data = []
    for full in items:
        with open(full, "rb") as f:
            data.append((os.path.relpath(full, folder).replace(os.sep, "/"), f.read()))
    base = os.path.basename(folder.rstrip(os.sep)) or "folder"
    results, sha = _step(root, data, lambda n: f"link folder {base}")
    added = sum(1 for r in results if r["status"] == "added")
    return {"linked": True, "files_catalogued": added, "skipped": skipped + len(results) - added, **_result(sha, root)}
