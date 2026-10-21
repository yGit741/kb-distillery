---
name: share-kb
description: >-
  Publish the wiki graph + explorer as a web site: deploy main to the private Cloudflare Worker
  (Google sign-in), check deploy status, roll back, and later build public snapshots / the time
  machine. Use for share the site, publish, deploy main, deploy status, snapshot the site, time
  machine, rollback the site. Do NOT use for export-kb (a zip for an LLM) or for kb-snapshot
  (an annotated kb-x.y.z tag); never run deploy-main with --force unless the user asks.
---

# share-kb

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `share the site`, `publish`, `publish the kb`, `deploy main`, `deploy the site`
- `deploy status`, `is the site up to date`, `share status`
- `rollback the site`, `roll back the deploy`
- `snapshot the site`, `public snapshot`, `time machine` (builder / snapshots land in their own PRs; say so if the subcommand is missing)

## Do NOT

- Confuse with `export-kb` (zip of wiki + think for an external LLM) or `kb-snapshot` (version tag / restore)
- Pass `--force` on your own — it bypasses the never-older guard; only when the user says force
- Deploy a public snapshot without `share audit` (W2b) — the private site is the only default target
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
pixi run test-worker                       # node --test of worker/auth.js
```

Autodeploy: every `kb(op)` commit, `ship merge` and the nightly sync trigger `deploy-main` in the
background (`KB_SHARE_AUTODEPLOY=0` opts out). Log: `~/Library/Logs/thesis-kb-share.log`;
dashboard nav shows the chip (green deployed · deploying · skipped · red failed → `/share-log`).

## Agent steps

1. `pixi run share -- status` — read the chip state first; `deployed` + current version → nothing to do.
2. On request: `pixi run share -- deploy-main` and report the state: `deployed`, `skipped-same`
   (live already has this sha), `skipped-older` (live is newer — never downgrade), `refused-no-access`
   (the Google gate is down: fix the Worker vars/secrets, nothing was uploaded), `failed` (read the log).
3. Rollback on request: `pixi run share -- rollback`; if the result says the auth gate is down, say so loudly.
4. First-time setup (user-owned): Worker secrets `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`
   (`npx wrangler@4.151.3 secret put … --name kb`); client id via `share config` or `KB_SHARE_GOOGLE_CLIENT_ID`.

## Output

Nothing in the vault. `.cache/share/status.json` (gitignored), the share log, and a new Worker
version at `https://kb.yonatan-magen-thesis.workers.dev` tagged `kb-share <sha> <version> <profile>`.

## Quality bar

The reported state matches `share status`; unauthenticated `curl -I` on the site gives 302 → `/auth/login`.

## Next step

`kb-history` to confirm which version is live vs. main; `export-kb` if an LLM needs the text instead.
