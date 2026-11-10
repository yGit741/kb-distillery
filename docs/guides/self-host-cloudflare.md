# Self-host behind Cloudflare Tunnel and Access

Run the app on one machine and reach it at a name on your own domain. Cloudflare Tunnel carries the traffic out from your machine, so no inbound port is opened. Cloudflare Access asks people to sign in and sends the app a signed token that proves who they are.

This guide covers one user per instance. For the rules every setup shares, see [Self-host behind any proxy](self-host-any-proxy.md).

## What you need

- A domain on Cloudflare, and a Zero Trust account (the free plan is enough for one user).
- `cloudflared` installed on the machine that runs the app.
- `distill` installed there with a knowledge base (see [Getting started](../getting-started.md)).

## Put Access in front of a name

In the Zero Trust dashboard:

1. Create a Tunnel and route a public hostname, for example `kb.example.com`, to the service `http://127.0.0.1:8765`. Leave the HTTP Host Header option empty so the original host reaches the app.
2. Create a self-hosted Access application for `kb.example.com`, with one allow policy that includes only `me@example.com`.
3. Copy the application's Audience (AUD) tag from its overview page. Note your team name; the token keys live at `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`.

## Start the app

Keep the app on loopback. The tunnel connects from the same machine.

```bash
export KB_AUTH=proxy
export KB_AUTH_EMAIL=me@example.com
export KB_AUTH_JWKS_URL=https://<team>.cloudflareaccess.com/cdn-cgi/access/certs
export KB_AUTH_AUDIENCE=<the AUD tag>
python -m kb_distillery.server --kb <id|path> --port 8765 --no-open
```

- Access sends a signed token in `Cf-Access-Jwt-Assertion`. The app checks the signature against `KB_AUTH_JWKS_URL`, requires an expiry, and requires the token's email to equal `KB_AUTH_EMAIL`.
- `KB_AUTH_AUDIENCE` is mandatory whenever `KB_AUTH_JWKS_URL` is set. One key set signs tokens for every application in your team, so without the audience a token issued for another application would pass. The server refuses to start without it.
- `KB_AUTH_JWKS_URL` must be an `https` address. The keys are cached for ten minutes and refetched when an unknown key id appears, at most once every 30 seconds.
- An `Authorization: Bearer <token>` header is accepted in place of `Cf-Access-Jwt-Assertion`.

Then run the tunnel:

```bash
cloudflared tunnel run <tunnel-name>
```

## Check it

- Open `https://kb.example.com`. Access asks you to sign in; after that the app loads.
- Call the local port directly with `curl -i http://127.0.0.1:8765/api/flags`. It answers `401 authentication required`, because the call carries no token.

## Things to know

- Do not point the tunnel at anything but the app. Every route, including the API docs and static files, needs a valid token.
- The tunnel must keep the original Host header. Saving a change checks that the request's Origin matches Host, and a mismatch is a 403 that says so.
- Deleting or recreating the Access application changes its AUD tag. Update `KB_AUTH_AUDIENCE` and restart.
- Prefer the key-set address above. If you cannot reach it from the machine, `KB_AUTH_JWT_KEY` takes a PEM public key (or a path to one) instead; the audience is optional with a static key, but still worth setting.
