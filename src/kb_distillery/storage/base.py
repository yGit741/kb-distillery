"""The storage connector interface: how a knowledge base reaches its raw sources.

A connector stores and returns objects under LOGICAL keys. A key is a forward-slash path relative to the kb root,
exactly as wiki pages and `meta/corpus.tsv` cite raw files (`raw/printed-docs/2014-book.pdf`). The key shape is
part of the contract: it stays the same whether the bytes sit in a folder, a Drive mount or a package's own store.

    list(prefix)       keys that start with `prefix`, sorted
    get(key)           the bytes
    put(key, data)     store bytes; raw sources are immutable, so an existing key is refused unless overwrite=True
    info(key)          size, mtime and sha1 (the manifest keeps the first 12 hex characters)
    local_copy(key)    a context manager yielding a readable local file path, for tools that need a file
    cached_path(key)   a local file path that stays valid for the process (not a connector method to implement:
                       the base class copies to a temp cache, a local store returns the file itself)
    auth()             whether the connector can reach its store right now, and what to do if not

Third parties implement `Connector` in a package and register it under the `kb_distillery.storage.connectors` entry-point group;
`tests/storage/test_connector_contract.py` is the suite every implementation must pass.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Iterator

SHORT_SHA1 = 12            # `meta/corpus.tsv` stores this many hex characters of an object's sha1


class StorageError(Exception):
    """A connector could not do what was asked; the message names the key or the store."""


class NotFound(StorageError):
    """No object under that key."""


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size: int
    mtime_ns: int
    sha1: str                          # full hex digest

    @property
    def short(self) -> str:
        """What `meta/corpus.tsv` records."""
        return self.sha1[:SHORT_SHA1]


@dataclass(frozen=True)
class AuthStatus:
    ok: bool
    message: str = ""                  # what is wrong and how to fix it, when not ok


def check_key(key) -> str:
    """The key if it is a valid logical key, else StorageError. Lexical only: no leading slash, no `..`,
    no empty segment, no backslash or NUL. Every connector calls this before touching its store."""
    if not isinstance(key, str) or not key:
        raise StorageError(f"storage key must be a non-empty string (got {key!r})")
    if key.startswith("/") or "\\" in key or "\x00" in key:
        raise StorageError(f"storage key {key!r} must be a relative forward-slash path")
    parts = key.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise StorageError(f"storage key {key!r} has an empty, `.` or `..` segment")
    return key


class Connector(ABC):
    """One store of raw sources. Subclasses set `name` and take the kb root first: `Cls(root, **options)`."""

    name: str = ""

    @abstractmethod
    def list(self, prefix: str = "") -> Iterator[str]: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def put(self, key: str, data: bytes, overwrite: bool = False) -> None: ...

    @abstractmethod
    def info(self, key: str) -> ObjectInfo: ...

    @abstractmethod
    def local_copy(self, key: str) -> AbstractContextManager[str]: ...

    @abstractmethod
    def auth(self) -> AuthStatus: ...

    def exists(self, key: str) -> bool:
        try:
            self.info(key)
        except NotFound:
            return False
        return True

    def cached_path(self, key: str) -> str:
        """A local file for `key` that stays valid for the life of the process: a web handler returning a file, a
        tool started later. A local store returns the file itself (it overrides this). Any other store gets this
        default: a copy kept in the system temp dir under the object's sha1, reused while the sha1 is unchanged."""
        info = self.info(key)
        who = f"{type(self).__module__}.{type(self).__qualname__}:{getattr(self, 'root', '')}"
        folder = os.path.join(tempfile.gettempdir(), "kb-raw-cache", hashlib.sha1(who.encode()).hexdigest()[:12],
                              info.short)
        path = os.path.join(folder, os.path.basename(key))
        if os.path.isfile(path) and os.path.getsize(path) == info.size:
            return path
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".part-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(self.get(key))
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        return path
