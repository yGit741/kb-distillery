"""A connector that keeps objects in memory: stands in for a third-party package in the contract and registry tests."""
import hashlib
import os
import tempfile
import time
from contextlib import contextmanager

from kb_distillery.storage import AuthStatus, Connector, NotFound, ObjectInfo, StorageError, check_key


class MemoryStore(Connector):
    name = "memory"

    def __init__(self, root, **options):
        self.root = root
        self.options = options
        self.objects = {}                       # key -> (bytes, mtime_ns)

    def list(self, prefix=""):
        yield from sorted(k for k in self.objects if k.startswith(prefix))

    def get(self, key):
        check_key(key)
        if key not in self.objects:
            raise NotFound(key)
        return self.objects[key][0]

    def put(self, key, data, overwrite=False):
        check_key(key)
        if key in self.objects and not overwrite:
            raise StorageError(f"{key!r} already exists")
        self.objects[key] = (bytes(data), time.time_ns())

    def info(self, key):
        data = self.get(key)
        return ObjectInfo(key=key, size=len(data), mtime_ns=self.objects[key][1], sha1=hashlib.sha1(data).hexdigest())

    @contextmanager
    def local_copy(self, key):
        data = self.get(key)
        fd, path = tempfile.mkstemp(suffix=os.path.splitext(key)[1])
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            yield path
        finally:
            os.remove(path)

    def auth(self):
        return AuthStatus(True)
