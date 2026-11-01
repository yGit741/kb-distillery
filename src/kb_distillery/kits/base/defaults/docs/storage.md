# Storage connectors

A knowledge base reaches its raw sources through a connector, so inputs can live in a local folder (the default), a Drive mount or a package's own store. Code: `src/kb_distillery/storage/`. Contract suite: `tests/storage/test_connector_contract.py`.

## The interface (`kb_distillery.storage.Connector`)

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
from kb_distillery.storage import raw
raw.exists("raw/web-clips/x.md")   raw.read_text(key)   raw.read_bytes(key)   raw.list("raw/printed-docs/")
raw.info(key).short                # the 12 hex characters meta/corpus.tsv stores
raw.path(key)                      # a local file valid for the process (the file itself for a local store)
raw.is_raw_key(value)              # the check serving code runs before it looks: valid key inside raw/
raw.put(key, data)                 # refused when the key exists: raw is immutable
```

`kb_distillery.storage.for_kb()` returns the connector itself, for code that needs `local_copy` or `auth`. `raw.path` is for a web handler or a tool that needs a file after the call returns; `local_copy` is the scoped version that cleans up.

`python -m kb_distillery.lint.raw_access` lists the modules that still touch `raw/` directly; `tests/storage/raw_access_baseline.txt` is their allowance, and a module you migrate must leave it.

## Google Drive (`gdrive`)

Reads the macOS Google Drive for desktop mount (`~/Library/CloudStorage/GoogleDrive-<account>/My Drive`). No OAuth, no API: the mount is a folder, Drive.app syncs it.

```toml
[storage]
connector = "gdrive"
[storage.options]
folder  = "Notes to Obsedian"   # folder under My Drive that plays the kb root; case/space/hyphen drift is tolerated
account = "me@gmail.com"        # only when several accounts are mounted
# mount = "/path/to/GoogleDrive-x"   # the mount itself, overriding the search (tests, odd setups)
```

Keys keep their shape: `raw/printed-docs/a.pdf` is `My Drive/<folder>/raw/printed-docs/a.pdf`. The mount is located on every call, so a kb with this connector still loads when Drive is not running; `auth()` then returns `ok=False` with what to do (install and sign in to Google Drive for desktop, open Google Drive.app, set `account`, fix `folder`), and reads and writes raise `StorageError` with the same message. `put` is refused for an existing key (raw stays immutable); `local_copy`/`cached_path` return the mounted file itself (Drive downloads it on first read). Contract tests run it against a temp directory standing in for the mount (`GDriveContract`). An API/OAuth variant is not built.

## Writing a connector in a package

Subclass `kb_distillery.storage.Connector` (constructor `Cls(root, **options)`), then register it:

```toml
# your package's pyproject.toml
[project.entry-points."kb_distillery.storage.connectors"]
my-store = "my_pkg.store:MyStore"
```

A package cannot take a built-in name (`local-folder`, `gdrive`). Run the contract suite against your class: copy the `MemoryStoreContract` pattern in the test file and give it a `make()`.

## Rules

- `put` never overwrites raw sources by default; `raw/` stays immutable.
- `local_copy` of a local store is the file itself; remote stores copy to a temp file and remove it on exit.
- Not yet moved onto connectors: the modules that read `raw/` directly (Phase 3 PR 3, in batches).
