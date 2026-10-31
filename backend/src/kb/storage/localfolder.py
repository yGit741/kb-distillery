"""The built-in connector: raw sources in a folder next to the kb (the default, and what every kb used before)."""
from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from typing import Iterator

from .base import AuthStatus, Connector, NotFound, ObjectInfo, StorageError, check_key


class LocalFolder(Connector):
    name = "local-folder"

    def __init__(self, root: str, **options):
        if options:
            raise StorageError(f"local-folder takes no options (got {sorted(options)})")
        self.root = os.path.abspath(root)

    def _path(self, key: str) -> str:
        return os.path.join(self.root, *check_key(key).split("/"))

    def list(self, prefix: str = "") -> Iterator[str]:
        if prefix:
            if prefix.startswith("/") or ".." in prefix.split("/"):
                raise StorageError(f"storage prefix {prefix!r} must be a relative path without `..`")
        start = os.path.join(self.root, *prefix.split("/")[:-1]) if "/" in prefix else self.root
        found = []
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for fn in filenames:
                if fn.startswith("."):
                    continue
                key = os.path.relpath(os.path.join(dirpath, fn), self.root).replace(os.sep, "/")
                if key.startswith(prefix):
                    found.append(key)
        yield from sorted(found)

    def get(self, key: str) -> bytes:
        try:
            with open(self._path(key), "rb") as f:
                return f.read()
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            raise NotFound(f"no object {key!r} in {self.root}") from None

    def put(self, key: str, data: bytes, overwrite: bool = False) -> None:
        path = self._path(key)
        if os.path.exists(path) and not overwrite:
            raise StorageError(f"{key!r} already exists; raw sources are immutable (overwrite=True to replace)")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".put-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def info(self, key: str) -> ObjectInfo:
        path = self._path(key)
        try:
            st = os.stat(path)
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            h = hashlib.sha1()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        except (FileNotFoundError, NotADirectoryError):
            raise NotFound(f"no object {key!r} in {self.root}") from None
        return ObjectInfo(key=key, size=st.st_size, mtime_ns=st.st_mtime_ns, sha1=h.hexdigest())

    @contextmanager
    def local_copy(self, key: str):
        """The file itself: nothing is copied for a local store."""
        path = self._path(key)
        if not os.path.isfile(path):
            raise NotFound(f"no object {key!r} in {self.root}")
        yield path

    def cached_path(self, key: str) -> str:
        """The file itself, no copy and no hashing: this is the hot path for serving and reading local sources."""
        path = self._path(key)
        if not os.path.isfile(path):
            raise NotFound(f"no object {key!r} in {self.root}")
        return path

    def auth(self) -> AuthStatus:
        if os.path.isdir(self.root):
            return AuthStatus(True)
        return AuthStatus(False, f"folder {self.root} does not exist")
