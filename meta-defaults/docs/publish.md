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

Precedence: the kb's `[publish] publisher`, then the engine default: `$KB_PUBLISHER`, then `[publish] publisher` in
`~/.config/kb-distillery/engine.toml` (`$KB_ENGINE_CONFIG` moves it), then none (`NullPublisher`). Engine-only commands such as
`ship merge` select no kb, so they see only the engine default: to keep the deploy nudge on merges, set one.
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

## Keeping today's Cloudflare behaviour

Cloudflare is off until selected. To publish as before, add to `kbs/<id>/kb.toml`

```toml
[publish]
publisher = "cloudflare"
```

and, for commands that select no kb (`ship merge`, the nightly sync), create `~/.config/kb-distillery/engine.toml` with the
same two lines (or export `KB_PUBLISHER=cloudflare`). `pixi run share -- ...` is the Cloudflare code's own CLI and never
needs a publisher. The deploy owner (launchd) is its own process and is untouched.

## Core without a publisher

Nothing in core imports `kb.share` (`backend/tests/publish/test_core_without_share.py` blocks it and loads core). With no
publisher the API and dashboard report `chip.label = "no publisher"`, the hygiene checks find nothing, and a `kb(op)` commit
nudges nobody. `GET /api/share/status` keeps its shape.
