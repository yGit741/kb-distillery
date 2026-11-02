# Publishing

Publishing puts a static snapshot of a knowledge base on a web host. It is optional and it is a plugin. With no publisher configured, the engine runs unchanged and the app reports "no publisher".

## Choose a publisher

```toml
# kb.toml
[publish]
publisher = "cloudflare"
[publish.options]
account_id = "<your account id>"
subdomain  = "<your workers.dev subdomain>"
worker     = "<name of the live site Worker>"   # default "kb"
```

The first match wins: the `[publish]` table of the knowledge base, then `KB_PUBLISHER`, then `[publish]` in `~/.config/kb-distillery/engine.toml`, then none. `none` or an absent value means no publisher.

Cloudflare Workers is the built-in publisher. Other publishers are packages that register themselves. See [Add a publisher](../guides/add-a-publisher.md).

## What gets published

A build takes a git ref of the knowledge base: `main`, a commit, a tag `kb-x.y.z` or a version `x.y.z`. It produces a self-contained graph and explorer page.

There are two profiles:

- `private`: the full site, behind a sign-in.
- `public`: a snapshot with no sign-in. It can be limited to one scope or collection and its neighbours (`--scope`, `--hops`) or to the pages the Map view draws (`--predicate public`).

## Audit before you publish

```bash
pixi run distill share audit kb-1.2.3 --kb my-kb
pixi run distill share snapshot my-snapshot kb-1.2.3 --dry-run --kb my-kb
pixi run distill share snapshot my-snapshot kb-1.2.3 --kb my-kb
pixi run distill share list --kb my-kb
```

`audit` builds the public profile and scans it. It exits 1 when it finds flagged content. `snapshot` refuses to deploy while there are flags, unless you pass `--allow-flags`. A snapshot is served at `https://snapshot-<YYYYMMDD>-<name>.<subdomain>.workers.dev/`.

Other `share` commands: `build`, `versions`, `deploy-main`, `status`, `rollback`, `config`, `history`, `remove`, `prune`. See the [CLI reference](../reference/cli.md).

## Rules

- With the Cloudflare publisher selected, a knowledge commit can start a deploy of the live site in the background. Set `KB_SHARE_AUTODEPLOY=0` to turn that off. A snapshot is always a command you run.
- The engine core never imports a publisher. It asks a registry.
- `available()` and `status()` of a publisher read local state only.
- An account id, API token and subdomain are yours. The token goes in `CLOUDFLARE_API_TOKEN`, never in a committed file.

More: [publish.md](../../src/kb_distillery/kits/base/defaults/docs/publish.md)
