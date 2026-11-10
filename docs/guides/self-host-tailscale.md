# Self-host behind Tailscale

Run the app on one machine and open it from your other devices over your tailnet. Tailscale Serve terminates HTTPS, knows who is calling, and passes that identity to the app in a header. Nobody outside your tailnet can reach it.

This guide covers one user per instance. For the rules every setup shares, see [Self-host behind any proxy](self-host-any-proxy.md).

## What you need

- A machine that stays on, with `distill` installed and a knowledge base (see [Getting started](../getting-started.md)).
- Tailscale on that machine and on the devices you read from, with HTTPS certificates enabled for your tailnet.

## Start the app

Keep the app on loopback. Tailscale Serve connects from the same machine, so no other bind is needed.

```bash
export KB_AUTH=proxy
export KB_AUTH_EMAIL=me@example.com
export KB_AUTH_HEADER=Tailscale-User-Login
export KB_AUTH_TRUSTED_PROXY_CIDR=127.0.0.1/32,::1/128
python -m kb_distillery.server --kb <id|path> --port 8765 --no-open
```

- `KB_AUTH_EMAIL` is the one login allowed in. It is compared without regard to case.
- `KB_AUTH_HEADER` names the header that carries the login. The app reads it only from a direct connection inside `KB_AUTH_TRUSTED_PROXY_CIDR`; the same header from anywhere else is refused.
- The login must be an email address, because `KB_AUTH_EMAIL` must contain an `@`. A tailnet login that is a bare username can never match.
- If any of these is missing or invalid, the server exits with a message naming it.

## Publish it on the tailnet

```bash
tailscale serve --bg 8765
tailscale serve status
```

Serve prints an address such as `https://host.tailnet-name.ts.net`. Open it from any device on your tailnet.

Serve sets `Tailscale-User-Login` itself on every request it forwards. Do not use Tailscale Funnel for this app: Funnel is public and carries no login header, so every request would be refused.

## Check it

- Open the Serve address while signed in to Tailscale as `me@example.com`. The app loads.
- Open it from a device signed in as someone else, or call the local port directly with `curl -i http://127.0.0.1:8765/api/flags`. Both are answered with `401 authentication required`, because the direct call carries no identity.

## Things to know

- The proxy must keep the original Host header. Saving a change checks that the request's Origin matches Host, and a mismatch is a 403 that says so.
- `X-Forwarded-For` is never read. The app looks at the connection itself.
- A static `--host 0.0.0.0` bind is allowed in proxy mode, but is not needed here and widens who can reach the port. Prefer loopback.
