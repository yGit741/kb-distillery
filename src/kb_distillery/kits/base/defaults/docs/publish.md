# Publishing

Publishing a kb as a site is a plugin, not part of core. Core talks to the `kb_distillery.publish.Publisher` interface; a
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
`kb_distillery.publish.current()` never raises (a bad setting gives a `NullPublisher` that says why); `for_kb()` raises `PublishError`.

## The interface (`src/kb_distillery/hosting/base.py`)

Required: `available()`, `status(root)`, `publish(snapshot, dry_run=)`. Optional, with empty defaults:
`log_tail`, `request_publish` (a nudge, never raises), `rollback`, `snapshots`, `orphan_snapshots`, `audit`,
`account_api`. `status()` returns a dict with the keys `state, sha, kb_version, at, error, url` or None.
A `Snapshot(ref, name, public)` says what to publish: no name = the live site, a name = a named snapshot.

## Adding a publisher

Expose a `Publisher` subclass in the `kb.publishers` entry-point group
(`[project.entry-points."kb.publishers"] my-host = "my_pkg.host:MyHost"`). A package cannot take a built-in name
(`none`, `cloudflare`). Subclass `PublisherContract` from `tests/publish/test_publisher_contract.py` with a
`make()` that wires fakes: a contract test never reaches a real site, account or tool.

## Rules

- Core never imports a publisher's code; it asks the registry. `kb_distillery.publish.cloudflare` is the Cloudflare publisher's code.
- `available()` and `status()` are pure local reads.
- Nothing publishes by itself: the Cloudflare publisher keeps `KB_SHARE_AUTODEPLOY=0` and its single deploy owner.

## Keeping today's Cloudflare behaviour

Cloudflare is off until selected. To publish as before, add to `~/knowledge/<id>/kb.toml`

```toml
[publish]
publisher = "cloudflare"
```

and, for commands that select no kb (`ship merge`, the nightly sync), create `~/.config/kb-distillery/engine.toml` with the
same two lines (or export `KB_PUBLISHER=cloudflare`). `pixi run share -- ...` is the Cloudflare code's own CLI and never
needs a publisher. The deploy owner (launchd) is its own process and is untouched.

## Core without a publisher

Nothing in core imports `kb_distillery.publish.cloudflare` (`tests/publish/test_core_without_share.py` blocks it and loads core). With no
publisher the API and dashboard report `chip.label = "no publisher"`, the hygiene checks find nothing, and a `kb(op)` commit
nudges nobody. `GET /api/share/status` keeps its shape.

## The Cloudflare publisher on your own account

The publisher works for any Cloudflare account; nothing about an account is fixed in its code. (The older `kb_distillery.publish.cloudflare` code keeps
the original owner's values as the defaults used when nothing is configured, so existing sites and links do not change.)

What the account needs:

- an **account id** (Cloudflare dashboard, Workers & Pages, right-hand side);
- an **API token** with permission to edit Workers scripts, read account analytics (view counts) and, only for the metrics
  store (`metrics d1`), edit D1 databases. Put it in `CLOUDFLARE_API_TOKEN` (or log in with `npx wrangler login`); it never goes in a
  file that is committed;
- a `workers.dev` **subdomain** registered on the account, and `node`/`npx` for wrangler.

Configuration (kb.toml, or the same table in the engine config):

```toml
[publish]
publisher = "cloudflare"
[publish.options]
account_id = "<your account id>"
subdomain  = "<your workers.dev subdomain>"
worker     = "<name of the live site Worker>"     # default "kb"
```

The same three values can come from `KB_CLOUDFLARE_ACCOUNT_ID`, `KB_CLOUDFLARE_SUBDOMAIN`, `KB_CLOUDFLARE_WORKER`. A process uses one
account: the options must be set before the first publish. The sign-in allow-list and Google client id of the private site are
stored with `share config`.

Publishing a static snapshot (public, no sign-in; **not run here**, shown for the account owner):

```bash
pixi run share -- audit kb-1.2.3                     # what a public build would expose; exit 1 on flags
pixi run share -- snapshot my-snapshot kb-1.2.3 --dry-run
pixi run share -- snapshot my-snapshot kb-1.2.3      # -> https://snapshot-<YYYYMMDD>-my-snapshot.<subdomain>.workers.dev/
pixi run share -- list                               # the snapshots on the account
```

Existing snapshots are never touched by the plugin: their Worker names and URL shape
(`https://snapshot-<YYYYMMDD>-<name>.<subdomain>.workers.dev/`) are pinned by `tests/publish/test_snapshot_shape.py`.

## The upload inbox

The private site can take OKF bundles from a signed-in owner (`worker/inbox.js`, routes under `/api/inbox`): it validates a zip with the very checker the app uses, stores it in an R2 bucket bound as `KB_INBOX` as `pending`, and the owner's Mac imports it (`distill kb inbox pull`, `kb_distillery.import_kb.import_bundle`). User-facing steps, including the one-time `wrangler r2 bucket create` and the `INBOX_TOKEN` secret: `docs/guides/import-a-bundle.md`.

- **Bundling.** The Worker has no build step of its own, so `worker/build-okf.mjs` runs esbuild (from `web/node_modules`, a dependency of vite) over `worker/okf.entry.js`, which re-exports `checkBundle` from `web/src/lib/okf/checkBundle.ts`, and writes one dependency-free `okf.gen.js`. `deploy.render_worker_dir` runs it into the temporary Worker folder on every private deploy (it needs `pixi run web-install` once; the CI `worker` job runs it first), so the deployed checker is always the one in the commit. `okf.gen.js` is never committed. `pixi run worker-bundle` writes it beside the sources, and `pixi run test-worker` (the CI `worker` job) runs that first, so the inbox tests run against the real checker. `worker/zip.js` is the small zip reader (stored and deflate, via `DecompressionStream`): the zip-slip rules of `import_kb._safe_extract`, entry-count and unpacked-size limits, the same bundle-root choice as `find_bundle_root`.
- **Binding.** `[worker] inbox_bucket` in the share config (or `KB_SHARE_INBOX_BUCKET`) renders `"r2_buckets": [{"binding": "KB_INBOX", ...}]` into `wrangler.jsonc` of the private site only. Unbound: the routes answer 503.
- **Who.** Writes need a session on `ADMIN_EMAILS` (default `ALLOWED_EMAILS`) plus the `X-KB-Admin: 1` header and a same-origin `Origin`, exactly like the flag and snapshot panels. The Mac uses `Authorization: Bearer <INBOX_TOKEN>` (Worker secret) and may only list, download and report `imported`/`failed`.
- **Flag.** `inbox-pickup` (runtime, off): `daily-sync` pulls the inbox after the sync.
