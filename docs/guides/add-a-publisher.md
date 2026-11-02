# Add a publisher

A publisher puts a snapshot of a knowledge base on a host. The engine core talks to the `Publisher` interface in `kb_distillery.hosting`, which `kb_distillery.publish` re-exports. A publisher package implements it.

## The interface

Subclass `kb_distillery.hosting.Publisher` (`kb_distillery.publish.Publisher` is the same class). The constructor is `Cls(root=None, **options)`.

Required:

| Method | Does |
|---|---|
| `available()` | True when the publisher can run here. Reads local state only. |
| `status(root=None)` | A dict with `state`, `sha`, `kb_version`, `at`, `error` and `url`, or `None`. Reads local state only. |
| `publish(snapshot, dry_run=False)` | Publishes and returns a `PublishResult(state, url, version, error)`. |

Optional, with empty defaults: `log_tail`, `request_publish`, `rollback`, `snapshots`, `orphan_snapshots`, `audit`, `account_api`.

A `Snapshot(ref, name, public, options)` says what to publish. No `name` means the live site. A `name` means a named snapshot. `public` marks it as open to anyone.

## Register it

```toml
# pyproject.toml of your package
[project.entry-points."kb.publishers"]
my-host = "my_pkg.host:MyHost"
```

A package cannot use a built-in name (`none`, `cloudflare`).

## Select it

```toml
# kb.toml
[publish]
publisher = "my-host"
[publish.options]
site = "example"
```

The options are passed to the constructor as keyword arguments, after the root.

## Test it

`tests/publish/test_publisher_contract.py` holds `PublisherContract`. Mix it into a `unittest.TestCase` and return a publisher wired to fakes from `make()`. `tests/publish/fake_publisher.py` is a complete in-memory example.

A contract test must never reach a real site, account or tool.

## Rules

- Core does not import your code. It asks the registry.
- `available()` and `status()` do no network calls.
- Nothing publishes by itself. `publish` runs when a user or a configured hook asks for it.
- Keep credentials out of files that are committed.

More: [publish.md](../../src/kb_distillery/kits/base/defaults/docs/publish.md)
