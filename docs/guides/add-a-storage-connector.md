# Add a storage connector

A storage connector is how a knowledge base reaches its raw sources. The default connector reads a local folder. A second connector reads a mounted Google Drive folder on macOS. You can add your own in a separate package.

## The interface

Subclass `kb_distillery.storage.Connector`. The constructor is `Cls(root, **options)`. `root` is the knowledge base folder. `options` is the `[storage.options]` table.

| Method | Does |
|---|---|
| `list(prefix="")` | Returns the keys that start with `prefix`, sorted. |
| `get(key)` | Returns the bytes. Raises `NotFound` when the key is absent. |
| `put(key, data, overwrite=False)` | Stores bytes. Refuses an existing key unless `overwrite=True`. |
| `info(key)` | Returns `ObjectInfo(key, size, mtime_ns, sha1)`. |
| `local_copy(key)` | A context manager that yields a local file path. |
| `auth()` | Returns `AuthStatus(ok, message)`: can the store be reached now, and what to do if not. |

A key is a logical path relative to the knowledge base root, such as `raw/printed-docs/2014-book.pdf`. It has no leading `/`, no `..` and no empty segment. Use `check_key(key)` to validate it. The key shape does not change with the store, so page citations keep working.

Raw sources are immutable. `put` must refuse to replace a key unless the caller passes `overwrite=True`.

## A minimal connector

```python
import hashlib, time
from contextlib import contextmanager
from kb_distillery.storage import AuthStatus, Connector, NotFound, ObjectInfo, StorageError, check_key

class MemoryStore(Connector):
    name = "memory"

    def __init__(self, root, **options):
        self.root, self.options, self.objects = root, options, {}
    ...
```

`tests/storage/dummy_connector.py` is the full version.

## Register it

In the `pyproject.toml` of your package:

```toml
[project.entry-points."kb_distillery.storage.connectors"]
my-store = "my_pkg.store:MyStore"
```

A package cannot use a built-in name (`local-folder`, `gdrive`).

## Select it

```toml
# kb.toml
[storage]
connector = "my-store"
[storage.options]
bucket = "example"
```

Without a `[storage]` table, a knowledge base uses the local folder at its root.

## Test it

The contract suite is `tests/storage/test_connector_contract.py`. Copy the pattern: mix `ConnectorContract` into a `unittest.TestCase` and return a fresh, empty connector from `make()`.

```python
class MyStoreContract(ConnectorContract, unittest.TestCase):
    def make(self):
        return MyStore("/unused")
```

A contract test must not reach a real service.

## In engine code

Engine modules read raw files through the facade, which is bound to the current knowledge base's connector:

```python
from kb_distillery.storage import raw
raw.exists("raw/web-clips/x.md")
raw.read_text("raw/web-clips/x.md")
raw.list("raw/printed-docs/")
```

`kb_distillery.storage.for_kb()` returns the connector itself, for code that needs `local_copy` or `auth`.

Packaging and testing it as an installed extension: [Build an extension](build-an-extension.md).

More: [storage.md](../../src/kb_distillery/kits/base/defaults/docs/storage.md)
