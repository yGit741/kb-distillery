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
- `update the snapshot <name>`, `edit the snapshot I sent`, `point the <name> link at kb-x.y.z`, `snapshot history`,
  `roll back the snapshot`
- `remove snapshot <name>`, `delete the snapshot`, `prune snapshots`
- `time machine` (lands in its own PR; say so if the subcommand is missing)

## Do NOT

- Confuse with `export-kb` (zip of wiki + think for an external LLM) or `kb-snapshot` (version tag / restore)
- Pass `--force` on your own — it bypasses the never-older guard (on `deploy-main` and on
  `snapshot --replace` alike); only when the user says force
- Update a sent snapshot without saying so: `--replace` changes what a link the user already
  forwarded shows; name the old and new kb version in the reply (the CLI prints both)
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
pixi run share -- snapshot <name> <ref>    # audit, then publish as snapshot-<YYYYMMDD>-<name> (public); --allow-flags, --dry-run
pixi run share -- snapshot <name> <ref> --replace   # UPDATE a sent snapshot: same Worker, same link; refuses an older ref (--force)
pixi run share -- snapshot <name> <ref> --app --scope <slug> [--hops 0|1]   # SUBGRAPH: only a scope / collection / person page, its members and (hops 1, default) their neighbours; manifest records scope + hops
pixi run share -- snapshot <name> <ref> --app --predicate public [--view map]   # MAP ONLY: after the public cuts keep just the pages the app's Map view draws (kb.share.predicate = publicPredicate.ts: topics; linked concepts/collections; full/deep sources; no scope/distilled-think) — links, cards, bodies and search entries of dropped pages go too; `--view <id>` opens the graph on that view (home.view). Manifest records predicate, dropped, view; `audit` takes both flags
pixi run share -- list [--json]            # our snapshots: version, behind-main, deployed at, views 7d, updates (was kb-x), online
pixi run share -- history <name> [--json]  # every version a snapshot served, newest first, * = live; version ids for rollback
pixi run share -- rollback --worker <name> [--to <id>]   # a snapshot's previous version (no auth gate; kb is the default worker)
pixi run share -- remove <name>            # type the worker name to confirm (--yes skips); never kb
pixi run share -- prune [--apply]          # orphans (snapshot-* without a reachable manifest); foreign Workers only listed
pixi run test-worker                       # node --test of worker/auth.js + admin.js
```

Snapshots: `<ref>` is `main`, a commit, `kb-x.y.z` or `x.y.z`; the URL is
`https://snapshot-<YYYYMMDD>-<name>.yonatan-magen-thesis.workers.dev/` (date = deploy day, UTC).
Public builds exclude only `distilled-think`, `scope` and anything derived from e-mail (`raw:` under
`raw/emails/`, i.e. email-thread `conversation-` pages); person pages, LLM chats and ordinary `raw/`
paths are public (owner decision 2026-10-24: mails involve someone else, chats and profiles do not).
Audit flags: email-derived pages or `raw/emails/` paths in prose (`email-source`), e-mail addresses,
phone-number patterns, `distilled-think`. Cloudflare is the registry (`snapshot-`
prefix + `kb-share` deploy message); credentials come from `CLOUDFLARE_API_TOKEN` or wrangler's
login. Views show `0*` with a note when analytics is unavailable.

**One deploy owner — agents never deploy.** `kb.share.owner` (launchd `com.thesis-kb.deploy-owner`,
KeepAlive) is the only process that deploys main: it fetches origin/main, builds each sha once into
`.cache/share/build/<sha>`, `versions upload` → `versions deploy @100` → health (auth gate, `/app`, live
version = uploaded) → rolls back to the previous version on failure; network errors retry 10 s/60 s/300 s.
It posts `deployed`/`rolled-back` on the merged PR and its round. Every `kb(op)` commit, `ship merge` and
the nightly sync only **nudge** it (touch `.cache/share/wake`; `KB_SHARE_AUTODEPLOY=0` opts out,
`KB_SHARE_DIRECT=1` — the user only — runs the old `deploy-main` path). The user installs it once with
`pixi run install-deploy-owner` (log `~/Library/Logs/thesis-kb-deploy-owner.log`); state:
`pixi run python -m kb.share.owner status`. `deploy-main.yml` deploys daily only when the owner has not
deployed for 24 h. `.claude/settings.json` denies agents `share -- deploy*`/`rollback*`, every wrangler
deploy/upload/rollback and `owner run`; agents may run `share -- status`/`audit`/`build` and
`owner status`/`nudge`. Log: `~/Library/Logs/thesis-kb-share.log`;
dashboard nav shows the chip (green deployed · deploying · skipped · red failed → `/share-log`).

## Agent steps

1. `pixi run share -- status` — read the chip state first; `deployed` + current version → nothing to do.
2. On request ("deploy main"): nudge the owner (`pixi run python -m kb.share.owner nudge`) and report
   `owner status`; `owner once` and a direct `share -- deploy-main` are the user's commands. States: `deployed`, `skipped-same`
   (live already has this sha), `skipped-older` (live is newer — never downgrade), `refused-no-access`
   (the Google gate is down: fix the Worker vars/secrets, nothing was uploaded), `failed` (read the log).
3. Rollback on request: give the user `! pixi run share -- rollback` (denied for agents); if the result says the auth gate is down, say so loudly.
4. Snapshot on request: `share audit <ref>` → show the flag counts → `share snapshot <name> <ref>`
   → give the URL. `share list` for status; `share remove <name>` / `share prune` only after the
   user confirms what will be deleted.
5. **Update a snapshot that was already sent** ("edit the snapshot", "point the link at the new
   version"): `share snapshot <name> <ref> --replace`. The link stays the same and starts serving
   `<ref>`; the recipient sees the new kb version and build date in the footer (the URL keeps its
   creation date). Safe because: the audit runs again; `skipped-same` means nothing to do;
   `skipped-older` is refused — an older ref downgrades what the recipient already saw, so only
   the user's explicit "force" adds `--force`; every earlier version stays on Cloudflare —
   `share history <name>` is the audit trail, `share rollback --worker <name>` the undo. Report
   the old → new version the CLI prints. Never `remove` + re-`snapshot` to "update": that
   changes the URL (new date) and drops the history.
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
7-day views, built date and online state, with Open / Copy link / Update… / Delete (type the Worker
name to confirm), shows an orphan / "not ours" banner from a **dry-run** prune, and a "New
snapshot" box that builds `pixi run share -- snapshot <name> kb-x.y.z` for you to run on the Mac;
"Update…" fills the box in replace mode (`--replace`, same link) and warns when a typed name is
already taken (creating, updating and `prune --apply` stay CLI-only).

API (`share/admin.js`, behind the sign-in session + `ALLOWED_EMAILS` (or `ADMIN_EMAILS`)
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
it (`MAX_HTML_BYTES` in `backend/src/kb/share/build.py`). Growth comes from embedded page bodies, the graph
and the digestion rows — shrink those, do not raise the constant.

## Quality bar

The reported state matches `share status`; unauthenticated `curl -I` on the site gives 302 → `/auth/login`.

## App build (default for `deploy-main`)

Same site, built from the React app under `frontend/` instead of the iframe shell. `deploy-main` (the
daily private deploy) builds it by default — `--legacy` builds the old shell instead, and a layout switch at
an already-deployed sha needs `--force`. `build`, `audit` and `snapshot` still need `--app` (public
snapshots stay on the legacy shell).

```bash
pixi run share -- build main --profile public  --app    # graph + pages
pixi run share -- build main --profile private --app    # + the read-only lifecycle view
pixi run share -- audit main --app                      # same audit, on the app build
pixi run share -- snapshot <name> main --app --dry-run  # audit + render the Worker dir, no deploy
pixi run share -- deploy-main --dry-run              # --legacy for the iframe shell
```

- Output `.exported/share/<ref>-app/`: `index.html` (carries the data blob in `<script id="kb-data">`,
  the id the audit scans) + `assets/` + `manifest.json` (`layout: "app"`, `sha256` = digest of the whole
  tree). The 25 MiB guard applies to every file; the Worker gets `not_found_handling =
  single-page-application` for this layout only.
- Data is the legacy `collect_data` / `collect_lifecycle` / `apply_profile`, so the public privacy cuts are
  the same code. The frontend is `vite build --mode share` per profile (`VITE_SHARE_PROFILE`), built into
  `frontend/dist-share/<profile>/` (gitignored) and rebuilt when `frontend/src` changes; needs
  `pixi run web-install` once. Chat, ops, pipeline, scopes and every mutation are not imported by the
  share builds (`frontend/src/routes/modules.share-*.ts`), not hidden: `/chat` is "Not Found".
- Frontend source comes from this checkout; a viewer ref older than this feature is refused (use
  `--viewer-worktree` while it is unmerged). Same content + same frontend = same bytes.
- **Switching the default later** (own PR, after the checks in the migration plan): pass `app=True` in
  `deploy.deploy_main` and `snapshots.audit_build`, make `--app` default on in `build.register`, `deploy-main`
  and `snapshots.register`, then delete the legacy shell, `static/kb-static.js`, the regex inliner and
  `frontend/src/share/search.test.ts` (it compares against the shim). Old `kb-*` tags keep building through
  their own viewer (`--viewer`).

## Next step

`kb-history` to confirm which version is live vs. main; `export-kb` if an LLM needs the text instead.
