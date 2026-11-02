# Config files and environment

## Where settings live

| Place | Holds |
|---|---|
| `kb.toml` of a knowledge base | Its kit, types, storage and publisher. See [kb.toml](kb-toml.md). |
| `~/.config/kb-distillery/` | Your settings that belong to no knowledge base. |
| Environment variables | Per-run choices. |
| `src/kb_distillery/kits/base/defaults/flags.toml` | The feature flag registry. |

## ~/.config/kb-distillery/

| File | Holds |
|---|---|
| `anthropic_key` | Your Anthropic API key, if you do not use `ANTHROPIC_API_KEY`. Keep it out of any repository. |
| `share.toml` | Publisher settings: who may sign in, the Cloudflare account subdomain, the Home tour. `KB_SHARE_CONFIG` or `<kb>/.cache/share/share.toml` take precedence. The tracked template is `src/kb_distillery/publish/cloudflare/share.example.toml`, with placeholders only. Secrets never go in it. |
| `engine.toml` | Engine defaults. Today: `[publish] publisher`, for commands that select no knowledge base. `KB_ENGINE_CONFIG` moves it. |
| `keys/` | Keys for optional services, such as `s2` for the Semantic Scholar API. |
| chat settings, usage ledger | Written by the app. |

The engine never moves your files. An older config folder is reported by `distill doctor`, which prints the command to move it.

Passwords for mail are stored in the macOS keychain, not in files.

## Feature flags

`flags.toml` has one `[[flag]]` table per flag. Keys: `name`, `description`, `owner`, `created`, `expires`, `kind` (`build` or `runtime`), `default` and `envs` (a value per environment: `local`, `private`, `public`). A flag has an `expires` date. An expired flag is a lint error, so remove it or renew it. The app lists flags at `GET /api/flags`.

## Environment variables

Knowledge base selection:

| Variable | Meaning |
|---|---|
| `KB` | The id or path of the knowledge base to use. |
| `KB_DISTILLERY_HOME` | Parent folder of knowledge bases. Default `~/knowledge`. |
| `KB_BASES_DIR` | Replaces the above. Meant for tests. |
| `KB_KITS_DIR` | Another kits folder. Meant for tests and kit development. |

Models:

| Variable | Meaning |
|---|---|
| `KB_LLM_BACKEND` | `subscription`, `api` or `batch`. Default `subscription`. A `--backend` option wins. |
| `ANTHROPIC_API_KEY` | Key for the `api` and `batch` backends. |

Git and operations:

| Variable | Meaning |
|---|---|
| `KB_NO_PUSH` | `1` commits without pushing. |
| `KB_OPS_DISABLE` | `1` skips the commit of wrapped operations. |
| `KB_OPS_STRICT` | `1` blocks wiki writes outside an open operation. `0` only warns. |
| `KB_POLICY` | `warn` or `enforce` for the git hook policy. |
| `KB_CI` | `1` for checkouts where raw binaries are not present. The linter reads the manifest instead. |
| `KB_OFFLINE` | Set to skip network lookups in `resolve`. |

Publishing:

| Variable | Meaning |
|---|---|
| `KB_PUBLISHER` | Publisher name when `kb.toml` sets none. |
| `KB_CLOUDFLARE_ACCOUNT_ID`, `KB_CLOUDFLARE_SUBDOMAIN`, `KB_CLOUDFLARE_WORKER` | Cloudflare publisher options. |
| `CLOUDFLARE_API_TOKEN` | API token for the Cloudflare publisher. |
| `KB_SHARE_AUTODEPLOY` | `0` turns off background deploys after knowledge commits. |

App:

| Variable | Meaning |
|---|---|
| `KB_QMD_PORT` | Port of the local search service. Default 8766. |
| `KB_BACKLOG_DIR` | Folder of the local backlog. |

People who change the engine also use `KB_APP_CONFIG`, the path to the GitHub App file that `ship` uses to act on pull requests.

`KB_ROOT` and `KB_LIVE` are set by the engine for processes it starts. Do not set them.
