# Import a bundle

An OKF bundle (the contents of a kb's `wiki/`: a folder, a `.zip`, or a git repository) always becomes a **new** knowledge base on your Mac. Kbs live on the Mac and nowhere else; an import never touches an existing kb and never publishes anything.

## Locally

In the app, use the Import dialog. The bundle is checked first; errors block the import and nothing is written.

## From the command line

```bash
distill kb import ./notes.zip --id my-notes --dry-run   # check only: id, page count, errors, warnings
distill kb import ./notes.zip --id my-notes             # a folder, a .zip, or https://… / git@… (optional #ref)
```

`--kit` picks the ontology kit (default `base`), `--dir` the parent folder (default `~/knowledge`). Details: [CLI reference](../reference/cli.md#kb).

## From the site inbox

On the deployed private site a signed-in **owner** (the sign-in allow-list) can upload a bundle. The Worker checks it with the same checker as the app, refuses unsafe zips (absolute paths, `..`, symlinks) and anything over the size limit (25 MiB by default, `INBOX_MAX_BYTES`), and parks it in a private R2 bucket as `pending`. A git URL is only recorded; your Mac does the clone. Nothing is imported or published by the site: the Mac picks the item up.

| Route (all behind the sign-in) | What |
|---|---|
| `POST /api/inbox/validate` | the checker report for a zip or `{"git_url": …}`; stores nothing |
| `POST /api/inbox` | store as pending (`?id=` `&kit=` `&name=`, or those fields in the JSON); an invalid bundle is a 422 with its report |
| `GET /api/inbox` | list the items (`?status=pending\|imported\|failed`) |
| `GET /api/inbox/<item>` , `/bundle` , `POST /api/inbox/<item>/status` | the record, the zip, and the Mac's report of `imported` or `failed` |

On the Mac:

```bash
distill kb inbox list [--status pending|imported|failed|all] [--json]
distill kb inbox pull [--dir PARENT] [--dry-run]     # import each pending item as a new kb, then mark it imported (with the kb id) or failed (with the error)
```

`pull` talks to the site with an inbox token (`$KB_INBOX_TOKEN`, or the macOS keychain item `kb-inbox-token`; it is never printed) and does not follow redirects. The site is `$KB_INBOX_URL`, or else the url of the configured publisher's last deploy. To run it every night, turn on the flag `inbox-pickup` on the Mac (off by default; `daily-sync` then calls `pull` after the sync, and a site that is down never fails the sync). It is a runtime flag read from this Mac's override (the app's System > Flags tab, or `meta/.ops/flags.json`); the copy of the flag list on the site does nothing for the Mac.

### One-time set-up (the owner, on their own account)

Nothing here is run by the engine or by agents.

```bash
# 1. the private bucket for uploads
npx wrangler@4.151.3 r2 bucket create kb-inbox

# 2. a token only your Mac and the Worker know: generated into a shell variable, never written to a file
TOKEN="$(openssl rand -base64 32 | tr -d '\n=')"
security add-generic-password -s kb-inbox-token -a "$USER" -w "$TOKEN"                       # the Mac reads it from the keychain
printf %s "$TOKEN" | npx wrangler@4.151.3 secret put INBOX_TOKEN --name kb                    # the Worker's copy
unset TOKEN
```

3. Bind the bucket: add `inbox_bucket = "kb-inbox"` under `[worker]` in `~/.config/kb-distillery/share.toml` (or set `KB_SHARE_INBOX_BUCKET`); the next deploy renders the binding `KB_INBOX`. Until then the inbox routes answer 503 and `validate` still works.
4. Deploy as usual. The deploy bundles the checker into the Worker (how: the "upload inbox" section of `publish.md` in the base kit's docs).
5. Optionally turn on `inbox-pickup` for the nightly run.
