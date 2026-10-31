"""Raw sources by logical key, through the current knowledge base's storage connector.

The shape engine modules use instead of `open(os.path.join(ROOT, "raw", ...))`:

    from kb.storage import raw
    raw.exists("raw/web-clips/x.md")        raw.read_text("raw/web-clips/x.md")      raw.read_bytes(rel)
    raw.list("raw/printed-docs/")           raw.info(rel).short                       raw.path(rel)    # a local file
    raw.put("raw/inbox/x.pdf", data)        raw.is_raw_key(value)

Keys are logical paths relative to the kb root, exactly as pages and `meta/corpus.tsv` cite them. A missing
key raises `NotFound` from `get`/`info`/`path`; `exists` is the question that does not raise. The connector is the
kb's `[storage]` choice (`kb.storage.for_kb`); it is resolved once per kb root and reused.
"""
from __future__ import annotations

import builtins
from functools import lru_cache

from kb import paths

from .base import Connector, NotFound, ObjectInfo, StorageError, check_key
from .registry import for_kb

RAW_PREFIX = "raw/"


@lru_cache(maxsize=8)
def _store_for(root: str) -> Connector:
    return for_kb(root=root)


def store() -> Connector:
    """The connector of the kb this process works on."""
    return _store_for(paths.ROOT)


def reset() -> None:
    """Forget resolved connectors (a test that changes the kb root or its [storage] table)."""
    _store_for.cache_clear()


def is_raw_key(value) -> bool:
    """True for a valid logical key inside the raw tree (`raw/...`): the check serving code runs before it looks."""
    try:
        return check_key(value).startswith(RAW_PREFIX)
    except StorageError:
        return False


def exists(key: str) -> bool:
    try:
        return store().exists(key)
    except StorageError:
        return False                      # an invalid key names nothing


def read_bytes(key: str) -> bytes:
    return store().get(key)


def read_text(key: str, encoding: str = "utf-8") -> str:
    return store().get(key).decode(encoding)


def list(prefix: str = "") -> "builtins.list[str]":          # noqa: A001 (the module is the namespace: raw.list)
    return builtins.list(store().list(prefix))


def info(key: str) -> ObjectInfo:
    return store().info(key)


def path(key: str) -> str:
    """A local file for `key` that stays valid for the process (the file itself for a local store)."""
    return store().cached_path(key)


def put(key: str, data: bytes, overwrite: bool = False) -> None:
    store().put(key, data, overwrite=overwrite)


__all__ = ["RAW_PREFIX", "Connector", "NotFound", "ObjectInfo", "StorageError", "exists", "info", "is_raw_key",
           "list", "path", "put", "read_bytes", "read_text", "reset", "store"]
