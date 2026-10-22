---
name: share-kb
description: >-
  Publish the wiki graph + explorer as a web site: deploy main to the private Cloudflare Worker
  (Google sign-in), deploy status, rollback, and PUBLIC snapshots (audit, snapshot, list, remove,
  prune). Use for share the site, publish, deploy main, deploy status, rollback the site, snapshot
  the site, list snapshots, remove snapshot, audit, time machine. Do NOT use for export-kb (a zip
  for an LLM) or kb-snapshot (a kb-x.y.z tag); never --force or --allow-flags unless the user asks.
---

# share-kb

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `share the site`, `publish`, `publish the kb`, `deploy main`, `deploy the site`
- `deploy status`, `is the site up to date`, `share status`
- `rollback the site`, `roll back the deploy`
- `audit`, `audit the public build`, `what would a snapshot expose`
- `snapshot the site`, `public snapshot`, `publish a snapshot <name>`
- `list snapshots`, `which snapshots are live`, `snapshot views`
- `remove snapshot <name>`, `delete the snapshot`, `prune snapshots`
- `time machine` (lands in its own PR; say so if the subcommand is missing)

## Do NOT

- Confuse with `export-kb` (zip of wiki + think for an external LLM) or `kb-snapshot` (version tag / restore)
- Pass `--force` on your own — it bypasses the never-older guard; only when the user says force
- Deploy a public snapshot past audit flags: `snapshot` runs `audit` itself and refuses on flags;
  pass `--allow-flags` only when the user has seen the flags and says so (snapshots are public, no sign-in)
- Touch the live Worker `kb` with snapshot commands — `remove` / `prune` refuse it by name
- `prune --apply` or `remove` without showing the dry run / asking first; `remove --yes` only when the user said yes
- Edit `wiki/` / `raw/` / `think/` — share only reads git; nothing here is a knowledge op
- Hand-edit `.cache/share/` or the rendered Worker dir; secrets never go in `share.toml`

## CLI

```bash
pixi run share -- deploy-main              # build main (private) → Worker kb, guarded
pixi run share -- deploy-main --dry-run    # render the Worker dir + print the wrangler command
pixi run share -- status                   # last outcome (.cache/share/status.json)
pixi run share -- rollback                 # previous version, then the auth gate is re-checked
pixi run share -- rollback --to <ID>
pixi run share -- config --google-client-id <id>   # store the OAuth client id (not secret)
pixi run share -- audit <ref>              # public build of <ref> in a temp dir: pages by type + privacy flags (exit 1 on flags)
pixi run share -- snapshot <name> <ref>    # audit, then publish as snapshot-<YYYYMMDD>-<name> (public); --replace, --allow-flags, --dry-run
pixi run share -- list [--json]            # our snapshots: version, behind-main, deployed at, views 7d, online
pixi run share -- remove <name>            # type the worker name to confirm (--yes skips); never kb
pixi run share -- prune [--apply]          # orphans (snapshot-* without a reachable manifest); foreign Workers only listed
pixi run test-worker                       # node --test of worker/auth.js + admin.js
```

Snapshots: `<ref>` is `main`, a commit, `kb-x.y.z` or `x.y.z`; the URL is
`https://snapshot-<YYYYMMDD>-<name>.yonatan-magen-thesis.workers.dev/` (date = deploy day, UTC).
Audit flags: person pages, `conversation-` / `ai-chat` pages, e-mail addresses, phone-number
patterns, `raw/` paths in prose, `distilled-think`. Cloudflare is the registry (`snapshot-`
prefix + `kb-share` deploy message); credentials come from `CLOUDFLARE_API_TOKEN` or wrangler's
login. Views show `0*` with a note when analytics is unavailable.

Autodeploy: every `kb(op)` commit, `ship merge` and the nightly sync trigger `deploy-main` in the
background (`KB_SHARE_AUTODEPLOY=0` opts out). Log: `~/Library/Logs/thesis-kb-share.log`;
dashboard nav shows the chip (green deployed · deploying · skipped · red failed → `/share-log`).

## Agent steps

1. `pixi run share -- status` — read the chip state first; `deployed` + current version → nothing to do.
2. On request: `pixi run share -- deploy-main` and report the state: `deployed`, `skipped-same`
   (live already has this sha), `skipped-older` (live is newer — never downgrade), `refused-no-access`
   (the Google gate is down: fix the Worker vars/secrets, nothing was uploaded), `failed` (read the log).
3. Rollback on request: `pixi run share -- rollback`; if the result says the auth gate is down, say so loudly.
4. Snapshot on request: `share audit <ref>` → show the flag counts → `share snapshot <name> <ref>`
   (`--replace` to redeploy an existing name in place) → give the URL. `share list` for status;
   `share remove <name>` / `share prune` only after the user confirms what will be deleted.
5. First-time setup (user-owned): Worker secrets `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`
   (`npx wrangler@4.151.3 secret put … --name kb`); client id via `share config` or `KB_SHARE_GOOGLE_CLIENT_ID`.

## What the private site contains

The private site (`deploy-main`, Google sign-in) is the shell with six tabs: **Graph · Explore ·
Health · Digestion · Lifecycle · Snapshots**. Health, Digestion and Lifecycle are the dashboard
pages rendered read-only from the content commit at build time (lint snapshot under `KB_CI`
semantics, the pipeline snapshot, the first-parent history with versions and `kb-*` snapshot tags);
`generated_at` is the commit date, so the time machine (`share build <old ref>`) shows those tabs as
of that commit and the bytes stay deterministic. Local state never ships: no working tree, open
sessions, nightly job, worktrees, branches, catalog logs, server info, file ages, absolute paths or
`think/` paths (the digestion snapshot keeps slug + proposal count for distill reviews). **Public
snapshots** (`share snapshot`) carry only Graph and Explore — none of those three tabs, their data or
the Snapshots panel — on top of the public profile's own cuts (no `distilled-think` pages, no
`raw`/`path`/`email`/`original_name` fields).

## Snapshots panel (private site)

The private site has a **Snapshots** tab (private builds only — public snapshots never contain it,
its script, or any `/admin/` path). It lists every `snapshot-*` Worker with kb version, behind-main,
7-day views, built date and online state, with Open / Copy link / Delete (type the Worker name to
confirm), shows an orphan / "not ours" banner from a **dry-run** prune, and a "New snapshot" box
that builds `pixi run share -- snapshot <name> kb-x.y.z` for you to run on the Mac (creating and
`prune --apply` stay CLI-only).

API (`meta/share/worker/admin.js`, behind the sign-in session + `ALLOWED_EMAILS` (or `ADMIN_EMAILS`)
+ header `X-KB-Admin: 1` + same-origin `Origin` for writes): `GET /admin/api/snapshots`,
`DELETE /admin/api/snapshots/<worker>` with body `{"confirm": "<worker>"}`, `POST /admin/api/prune`
(dry run). Behind-main in the panel is an approximation (patch difference within one x.y); the CLI's
`share list` is exact.

**One-time setup (user-owned):** Cloudflare dashboard → My Profile → API Tokens → Create custom
token with **Account → Workers Scripts → Edit** (list + delete) and **Account → Account Analytics →
Read** (views), scoped to this account. Copy it, then:

```bash
pbpaste | npx wrangler@4.151.3 secret put CF_API_TOKEN --name kb && pbcopy < /dev/null
```

`CF_ACCOUNT_ID` is rendered as a plain var by `deploy-main`. Until the secret exists the API answers
503 and the tab shows this hint. Never paste the token into chat or `share.toml`.

## Output

Nothing in the vault. `.cache/share/status.json` (gitignored), the share log, and a new Worker
version at `https://kb.yonatan-magen-thesis.workers.dev` tagged `kb-share <sha> <version> <profile>`;
snapshots are their own Workers (`.cache/share/status-snapshot-*.json`, never the main chip).

## Limits

The site is one `index.html` served from the Worker's static-assets directory: Cloudflare caps a
file at **25 MiB**. The build prints its size against that limit, warns from 80 % and refuses above
it (`MAX_HTML_BYTES` in `meta/share/build.py`). Growth comes from embedded page bodies, the graph
and the digestion rows — shrink those, do not raise the constant.

## Quality bar

The reported state matches `share status`; unauthenticated `curl -I` on the site gives 302 → `/auth/login`.

## Next step

`kb-history` to confirm which version is live vs. main; `export-kb` if an LLM needs the text instead.
