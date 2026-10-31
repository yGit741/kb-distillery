# Publishing

Publishing a kb as a site is a plugin, not part of core. Core talks to the `kb.publish.Publisher` interface; a
publisher package (Cloudflare is the first) implements it. With no publisher configured core runs unchanged and the
share screens say "no publisher configured".

## Picking a publisher

```toml
[publish]
publisher = "cloudflare"     # a built-in name or one a package registers; "none" or absent = no publisher
[publish.options]            # passed to the publisher as keyword arguments, after the kb root
```

Precedence: the kb's `[publish] publisher`, then the engine default `$KB_PUBLISHER`, then none (`NullPublisher`).
`kb.publish.current()` never raises (a bad setting gives a `NullPublisher` that says why); `for_kb()` raises `PublishError`.

## The interface (`backend/src/kb/publish/base.py`)

Required: `available()`, `status(root)`, `publish(snapshot, dry_run=)`. Optional, with empty defaults:
`log_tail`, `request_publish` (a nudge, never raises), `rollback`, `snapshots`, `orphan_snapshots`, `audit`,
`account_api`. `status()` returns a dict with the keys `state, sha, kb_version, at, error, url` or None.
A `Snapshot(ref, name, public)` says what to publish: no name = the live site, a name = a named snapshot.

## Adding a publisher

Expose a `Publisher` subclass in the `kb.publishers` entry-point group
(`[project.entry-points."kb.publishers"] my-host = "my_pkg.host:MyHost"`). A package cannot take a built-in name
(`none`, `cloudflare`). Subclass `PublisherContract` from `backend/tests/publish/test_publisher_contract.py` with a
`make()` that wires fakes: a contract test never reaches a real site, account or tool.

## Rules

- Core never imports a publisher's code; it asks the registry. `kb.share` is the Cloudflare publisher's code.
- `available()` and `status()` are pure local reads.
- Nothing publishes by itself: the Cloudflare publisher keeps `KB_SHARE_AUTODEPLOY=0` and its single deploy owner.
