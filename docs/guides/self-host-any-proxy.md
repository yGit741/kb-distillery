# Self-host behind any proxy

By default the app has no sign-in and refuses to listen on anything but loopback. Setting `KB_AUTH=proxy` turns that off in a controlled way: the app may listen beyond loopback, and then every request must prove who sent it. The proof comes from an identity-aware proxy that you run in front of it.

The app serves one user. Their email is `KB_AUTH_EMAIL`, and every request must carry exactly that identity. For step-by-step setups, see [Tailscale](self-host-tailscale.md) and [Cloudflare](self-host-cloudflare.md).

## The settings

| Variable | Meaning |
|---|---|
| `KB_AUTH` | `proxy` turns the mode on. Unset, empty or `loopback` is the default. Any other value stops the server. |
| `KB_AUTH_EMAIL` | The one email allowed in. Required. Compared without regard to case. |
| `KB_AUTH_JWKS_URL` | An `https` address of the proxy's signing keys. Use with `KB_AUTH_AUDIENCE`. |
| `KB_AUTH_AUDIENCE` | The token audience. Mandatory whenever `KB_AUTH_JWKS_URL` is set. |
| `KB_AUTH_JWT_KEY` | A PEM public key, or a path to one, in place of a key-set address. The audience is optional. Private keys and shared secrets are refused. |
| `KB_AUTH_HEADER` | Name of a header that carries the email, for proxies that do not sign tokens. |
| `KB_AUTH_TRUSTED_PROXY_CIDR` | Comma-separated address ranges the header may come from. Required with `KB_AUTH_HEADER`. |

You need at least one identity source: a key-set address, a public key, or a header with its ranges. The server checks all of this at start and exits with a message naming what is wrong.

## Two ways to prove identity

**A signed token.** The proxy puts a JWT in `Cf-Access-Jwt-Assertion` or `Authorization: Bearer`. The app verifies the signature, requires an `exp` claim (30 seconds of clock leeway), and reads the `email` claim. Only asymmetric algorithms are accepted (RS, PS, ES, EdDSA); `none` and shared-secret algorithms are refused. A request whose token fails is refused outright and never retried as a header.

**A trusted header.** The proxy sets the header named by `KB_AUTH_HEADER` to the user's email. The app believes it only when the direct network peer is inside `KB_AUTH_TRUSTED_PROXY_CIDR`. A request that repeats an identity header is refused.

`X-Forwarded-For` is never read, so it cannot be used to claim a trusted address.

## Binding

- With `KB_AUTH=proxy`, `--host` may be any address, for example `--host 0.0.0.0`. Without it, anything but loopback stops the server.
- Prefer loopback when the proxy runs on the same machine. If the proxy is on another host or in a container, bind a private interface and list only that proxy's range in `KB_AUTH_TRUSTED_PROXY_CIDR`.
- Every route needs the identity, including the API docs, static files and websockets. Without it the answer is `401 authentication required`.

## What the proxy must do

1. Authenticate the person before forwarding anything.
2. Keep the original Host header. Saving a change requires the request's Origin to match Host; the app answers 403 otherwise.
3. If you use a header, overwrite it on every request. Never pass through a value the client sent. Remove or replace it even on requests the proxy considers anonymous.
4. Reach the app only over a network you trust, and keep the app's own port closed to everything else.

## Example: oauth2-proxy

oauth2-proxy signs people in with your identity provider and forwards the email in `X-Forwarded-Email` when `--pass-user-headers` is on (the default).

```bash
export KB_AUTH=proxy
export KB_AUTH_EMAIL=me@example.com
export KB_AUTH_HEADER=X-Forwarded-Email
export KB_AUTH_TRUSTED_PROXY_CIDR=127.0.0.1/32
python -m kb_distillery.server --kb <id|path> --port 8765 --no-open
```

```bash
oauth2-proxy \
  --provider=oidc \
  --oidc-issuer-url=https://sso.example.com \
  --client-id=<client id> --client-secret=<client secret> \
  --email-domain=example.com \
  --authenticated-emails-file=/etc/oauth2-proxy/emails.txt \
  --upstream=http://127.0.0.1:8765 \
  --pass-host-header=true \
  --http-address=127.0.0.1:4180 \
  --cookie-secret=<random secret>
```

Put TLS in front of port 4180 (a reverse proxy or a load balancer) at a name such as `kb.example.com`, and forward the Host header unchanged. oauth2-proxy replaces `X-Forwarded-Email` with the signed-in user's value.

## Example: a company SSO header

If a gateway already signs people in and sets a header such as `X-Auth-Email`, name it:

```bash
export KB_AUTH=proxy
export KB_AUTH_EMAIL=me@example.com
export KB_AUTH_HEADER=X-Auth-Email
export KB_AUTH_TRUSTED_PROXY_CIDR=10.0.0.5/32
python -m kb_distillery.server --host 10.0.0.8 --kb <id|path> --port 8765 --no-open
```

Confirm with whoever runs the gateway that it overwrites `X-Auth-Email` on every request and that the app's port is reachable only from the gateway. If the gateway can issue a signed token instead, prefer that: a token does not depend on where the request came from.

## Check it

- Through the proxy, signed in as `me@example.com`: the app loads.
- Signed in as another account: `401 authentication required`.
- Straight to the app port, with no identity, or with a made-up `X-Auth-Email: me@example.com` from outside the trusted range: `401 authentication required`.
