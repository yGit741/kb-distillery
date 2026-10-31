# Storage connectors

A knowledge base reaches its raw sources through a connector, so inputs can live in a local folder (the default), a Drive mount or a package's own store. Code: `backend/src/kb/storage/`. Contract suite: `backend/tests/storage/test_connector_contract.py`.

## The interface (`kb.storage.Connector`)

| Method | Does |
|---|---|
| `list(prefix="")` | keys starting with `prefix`, sorted |
| `get(key)` | the bytes; `NotFound` when absent |
| `put(key, data, overwrite=False)` | store bytes; an existing key is refused unless `overwrite=True` (raw sources are immutable) |
| `info(key)` | `ObjectInfo(key, size, mtime_ns, sha1)`; `.short` is the 12 hex characters `meta/corpus.tsv` stores |
| `local_copy(key)` | context manager yielding a local file path, for tools that need a file |
| `auth()` | `AuthStatus(ok, message)`: can the store be reached now, and what to do if not |

**Keys are logical paths** relative to the kb root, as wiki pages and the manifest cite them: `raw/printed-docs/2014-book.pdf`. No leading `/`, no `..`, no empty segment. Whatever the store, the key shape does not change, so a page's citation keeps working.

## A kb picks one

```toml
# kbs/<id>/kb.toml (optional: no [storage] = the local folder at the kb root)
[storage]
connector = "local-folder"
[storage.options]        # keyword arguments after the kb root
```

In code, engine modules use the facade, which is bound to the current kb's connector:

```python
from kb.storage import raw
raw.exists("raw/web-clips/x.md")   raw.read_text(key)   raw.read_bytes(key)   raw.list("raw/printed-docs/")
raw.info(key).short                # the 12 hex characters meta/corpus.tsv stores
raw.path(key)                      # a local file valid for the process (the file itself for a local store)
raw.is_raw_key(value)              # the check serving code runs before it looks: valid key inside raw/
raw.put(key, data)                 # refused when the key exists: raw is immutable
```

`kb.storage.for_kb()` returns the connector itself, for code that needs `local_copy` or `auth`. `raw.path` is for a web handler or a tool that needs a file after the call returns; `local_copy` is the scoped version that cleans up.

`python -m kb.lint.raw_access` lists the modules that still touch `raw/` directly; `backend/tests/storage/raw_access_baseline.txt` is their allowance, and a module you migrate must leave it.

## Writing a connector in a package

Subclass `kb.storage.Connector` (constructor `Cls(root, **options)`), then register it:

```toml
# your package's pyproject.toml
[project.entry-points."kb.storage.connectors"]
my-store = "my_pkg.store:MyStore"
```

A package cannot take a built-in name (`local-folder`). Run the contract suite against your class: copy the `MemoryStoreContract` pattern in the test file and give it a `make()`.

## Rules

- `put` never overwrites raw sources by default; `raw/` stays immutable.
- `local_copy` of a local store is the file itself; remote stores copy to a temp file and remove it on exit.
- Not yet moved onto connectors: the modules that read `raw/` directly (Phase 3 PR 3, in batches).
