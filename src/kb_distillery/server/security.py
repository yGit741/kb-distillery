"""Server guards: bind address, Origin/Host on mutations, 4 MB body cap, raw path guard, opt-in proxy identity.

Default (loopback mode): the API serves a private vault to its owner on this machine and has no authentication; the
rules keep a web page in another tab (or a DNS-rebinding host name) from driving it.

`KB_AUTH=proxy` (self-hosting behind an identity-aware proxy): binding beyond loopback is allowed, and every request
must prove its user: a JWT signed by the proxy (`Cf-Access-Jwt-Assertion` or `Authorization: Bearer`, verified against
`KB_AUTH_JWKS_URL` with `KB_AUTH_AUDIENCE` (required there), or the static public key `KB_AUTH_JWT_KEY` (audience
optional); asymmetric algorithms only, `exp` required) or the header `KB_AUTH_HEADER`, accepted only from a direct peer inside
`KB_AUTH_TRUSTED_PROXY_CIDR` (the proxy must overwrite that header). The identity's email must equal `KB_AUTH_EMAIL`
(case-folded). X-Forwarded-For is never read. Mutations need an Origin on the request's own host.
"""
import ipaddress
import json
import logging
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

import anyio.to_thread
import jwt

from fastapi import HTTPException, Path, Request
from starlette.responses import JSONResponse

from kb_distillery.config import kb as kbconfig
from kb_distillery.services import corpus

MAX_BODY_BYTES = 4 * 1024 * 1024
# A bundle upload is a zipped folder of notes, and /api/inbox/files takes source files: these routes take a larger body than the 4 MB every other one gets.
UPLOAD_PATHS = frozenset({"/api/kb/import", "/api/kb/import/validate", "/api/inbox/files"})
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
CHAT_UPLOAD_PREFIX = "/api/chat/attachments"      # a 20 MB attachment plus the multipart form overhead
MAX_CHAT_UPLOAD_BYTES = 21 * 1024 * 1024
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


def is_loopback_host(host):
    if not host:
        return False
    host = host.strip().lower().strip("[]")
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def assert_loopback_bind(host):
    """Refuse to listen on anything but a loopback address unless `KB_AUTH=proxy` is configured (loopback mode has no
    authentication). An invalid `KB_AUTH` configuration is refused whatever the host."""
    config = load_auth_config()
    if config is None and not is_loopback_host(host):
        raise SystemExit(f"refusing to bind {host!r}: the API is local-only (use 127.0.0.1 or ::1, "
                         "or set KB_AUTH=proxy behind an identity-aware proxy)")


def require_loopback_origin(request: Request):
    """App-wide dependency. A mutating request must carry an Origin (browsers always send one on POST): a loopback
    one in loopback mode, one on the request's own host (host and port equal to `Host`) in proxy mode. A foreign or
    missing Origin is refused."""
    if request.method not in MUTATING:
        return
    origin = request.headers.get("origin")
    if origin is not None and auth_mode() == "proxy":
        host = (request.headers.get("host") or "").strip().lower()
        if host and urlparse(origin).netloc.lower() == host:
            return
    elif origin is not None and is_loopback_host(urlparse(origin).hostname):
        return
    if origin is not None and auth_mode() == "proxy":
        raise HTTPException(403, "cross-origin mutation refused: Origin must match Host (the proxy must preserve Host)")
    raise HTTPException(403, "cross-origin or origin-less mutation refused")


# ---- opt-in proxy identity (KB_AUTH=proxy) ----

AUTH_ENV = "KB_AUTH"
JWT_HEADER = "cf-access-jwt-assertion"
# Asymmetric only: the algorithm is never taken from the token, so `alg: none` and HS256 signed with the public key
# (algorithm confusion) are refused by construction.
JWT_ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA")
JWT_LEEWAY_S = 30
JWKS_TTL_S = 600
JWKS_REFETCH_MIN_S = 30
JWKS_TIMEOUT_S = 5


@dataclass(frozen=True)
class AuthConfig:
    email: str                      # case-folded
    jwks_url: str | None = None
    jwt_key: object | None = None   # a loaded public key
    audience: str | None = None
    header: str | None = None       # lower-cased header name
    trusted_cidrs: tuple = ()


def auth_mode() -> str:
    """`loopback` (default: `KB_AUTH` unset, empty or `loopback`) or `proxy`; anything else is a SystemExit."""
    mode = (os.environ.get(AUTH_ENV) or "loopback").strip().lower()
    if mode not in ("loopback", "proxy"):
        raise SystemExit(f"{AUTH_ENV}={mode!r} is not a mode: use proxy, or leave it unset for loopback")
    return mode


def _load_public_key(value):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    text = value.strip()
    if not text.startswith("-----BEGIN"):
        try:
            with open(os.path.expanduser(text), "rb") as fh:
                text = fh.read().decode()
        except OSError as exc:
            raise SystemExit(f"KB_AUTH_JWT_KEY: cannot read {text!r}: {exc}") from None
    try:
        return load_pem_public_key(text.encode())
    except ValueError:
        raise SystemExit("KB_AUTH_JWT_KEY must be a PEM public key (or a path to one); secrets are not accepted") from None


def load_auth_config() -> AuthConfig | None:
    """None in loopback mode; in proxy mode the validated config, or a SystemExit naming what is missing."""
    if auth_mode() != "proxy":
        return None
    env = os.environ
    email = (env.get("KB_AUTH_EMAIL") or "").strip().casefold()
    if "@" not in email:
        raise SystemExit("KB_AUTH=proxy needs KB_AUTH_EMAIL (the one user allowed in)")
    jwks_url = (env.get("KB_AUTH_JWKS_URL") or "").strip() or None
    if jwks_url and urlparse(jwks_url).scheme != "https":
        raise SystemExit("KB_AUTH_JWKS_URL must be an https URL")
    key_value = (env.get("KB_AUTH_JWT_KEY") or "").strip()
    jwt_key = _load_public_key(key_value) if key_value else None
    header = (env.get("KB_AUTH_HEADER") or "").strip().lower() or None
    cidr_text = (env.get("KB_AUTH_TRUSTED_PROXY_CIDR") or "").strip()
    try:
        cidrs = tuple(ipaddress.ip_network(c.strip(), strict=False) for c in cidr_text.split(",") if c.strip())
    except ValueError as exc:
        raise SystemExit(f"KB_AUTH_TRUSTED_PROXY_CIDR: {exc}") from None
    if header and not cidrs:
        raise SystemExit("KB_AUTH_HEADER needs KB_AUTH_TRUSTED_PROXY_CIDR (the proxy's address range)")
    if not (jwks_url or jwt_key or header):
        raise SystemExit("KB_AUTH=proxy needs KB_AUTH_JWKS_URL or KB_AUTH_JWT_KEY (a signed token), "
                         "or KB_AUTH_HEADER with KB_AUTH_TRUSTED_PROXY_CIDR (a trusted header)")
    audience = (env.get("KB_AUTH_AUDIENCE") or "").strip() or None
    if jwks_url and not audience:
        # one JWKS signs tokens for every app of a provider team: without aud, another app's token would pass
        raise SystemExit("KB_AUTH_JWKS_URL needs KB_AUTH_AUDIENCE (the application's audience, e.g. the Access AUD tag)")
    return AuthConfig(email=email, jwks_url=jwks_url, jwt_key=jwt_key, audience=audience, header=header,
                      trusted_cidrs=cidrs)


def _fetch_jwks(url):
    """GET the JWKS document (tests replace this; they never touch the network)."""
    with urllib.request.urlopen(url, timeout=JWKS_TIMEOUT_S) as resp:     # noqa: S310 (https enforced in config)
        return json.loads(resp.read())


_jwks_lock = threading.Lock()
_jwks_cache: dict = {}          # url -> (fetched_at, {kid: PyJWK})
_jwks_tried: dict = {}          # url -> time of the last fetch attempt, successful or not
log = logging.getLogger(__name__)


def _jwks_key(url, kid):
    """The signing key with this `kid` from the JWKS at `url`: cached for JWKS_TTL_S, refetched when stale or on an
    unknown kid. Any fetch attempt (a failed one too) waits JWKS_REFETCH_MIN_S after the last, so garbage tokens or a
    dead endpoint cannot make every request fetch. None when not found or the fetch fails."""
    with _jwks_lock:
        now = time.monotonic()
        fetched_at, keys = _jwks_cache.get(url, (None, {}))
        tried = _jwks_tried.get(url)
        stale = fetched_at is None or now - fetched_at > JWKS_TTL_S
        if (stale or kid not in keys) and (tried is None or now - tried > JWKS_REFETCH_MIN_S):
            _jwks_tried[url] = now
            try:
                keyset = jwt.PyJWKSet.from_dict(_fetch_jwks(url))
                keys = {k.key_id: k for k in keyset.keys if k.key_id}
                _jwks_cache[url] = (now, keys)
            except Exception as exc:  # noqa: BLE001 (a failed fetch or a bad document refuses the request)
                log.warning("KB_AUTH_JWKS_URL fetch failed: %s", exc)
        return keys.get(kid)


def _jwt_email(config, token):
    """The verified token's `email` claim, or None."""
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in JWT_ALGORITHMS:
            return None
        if config.jwt_key is not None:
            key = config.jwt_key
        else:
            jwk = _jwks_key(config.jwks_url, header.get("kid"))
            if jwk is None:
                return None
            key = jwk.key
        claims = jwt.decode(token, key, algorithms=list(JWT_ALGORITHMS), audience=config.audience,
                            leeway=JWT_LEEWAY_S,
                            options={"require": ["exp"], "verify_aud": config.audience is not None})
    except jwt.PyJWTError:
        return None
    email = claims.get("email")
    return email if isinstance(email, str) else None


def _peer_trusted(config, client):
    """Is the TCP peer (the ASGI scope's client, never X-Forwarded-For) inside the trusted proxy range?"""
    if not client:
        return False
    try:
        ip = ipaddress.ip_address(str(client[0]).strip("[]"))
    except ValueError:
        return False
    return any(ip in net for net in config.trusted_cidrs)


def authenticate(config, headers, client):
    """The request's email (case-folded) when it is the allowed user, else None.
    `headers` maps lower-cased names to values; `client` is the ASGI scope's (host, port)."""
    token = headers.get(JWT_HEADER)
    if not token:
        auth = headers.get("authorization", "")
        if auth[:7].lower() == "bearer ":
            token = auth[7:].strip()
    if token and (config.jwks_url or config.jwt_key is not None):
        email = _jwt_email(config, token)           # a bad token is refused, never retried as a header
    elif config.header and config.header in headers:
        if not _peer_trusted(config, client):
            return None                             # the identity header from outside the proxy range: a spoof
        email = headers[config.header]
    else:
        return None
    if not email:
        return None
    email = email.strip().casefold()
    return email if email == config.email else None


class ProxyAuthMiddleware:
    """Pure ASGI, outermost: in proxy mode every http and websocket request (docs, static files and 404s included)
    must carry the allowed user's identity, else 401. In loopback mode it passes everything through."""

    def __init__(self, app):
        self.app, self.config = app, load_auth_config()

    async def __call__(self, scope, receive, send):
        if self.config is None or scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers, repeated = {}, set()
        for name, value in scope["headers"]:
            key = name.decode("latin-1").lower()
            if key in headers:
                repeated.add(key)
            headers.setdefault(key, value.decode("latin-1"))
        identity_headers = {JWT_HEADER, "authorization", self.config.header}
        # in a worker thread: a JWKS fetch must not block the event loop
        if not repeated & identity_headers and await anyio.to_thread.run_sync(
                authenticate, self.config, headers, scope.get("client")) is not None:
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        return await JSONResponse({"detail": "authentication required"}, 401)(scope, receive, send)


# Mutating routes that touch no kb folder, matched whole (a path equals one, or continues after one + "/"): feature flags,
# chat turns and settings (their state lives outside the kb), graph and scope queries that only compute a read, and the
# routes that create a *new* kb elsewhere. Everything else that mutates is refused on a read-only kb, including chat
# sessions, recent steps, attachments and skills (they write under <kb>/.local).
READ_ONLY_OPEN = ("/api/flags", "/api/graph", "/api/scopes/resolve", "/api/chat/answer", "/api/chat/message",
                  "/api/chat/settings", "/api/chat/keys", "/api/kb/import", "/api/kb/inbox")
SELF_REFUSING = ("/api/sessions", "/api/chat/skills", "/api/favorites", "/api/views", "/api/recent")
READ_ONLY_OPEN_EXACT = ("/api/chat",)


def _read_only_open(path: str) -> bool:
    path = path.rstrip("/")
    return path in READ_ONLY_OPEN_EXACT or any(path == p or path.startswith(p + "/") for p in READ_ONLY_OPEN)


def require_writable_kb(request: Request):
    """App-wide dependency. On a read-only kb (example, `[kb] read_only`, $KB_READ_ONLY) every mutation is 403
    unless its route is in `READ_ONLY_OPEN`."""
    if request.method not in MUTATING or _read_only_open(request.url.path):
        return
    if not kbconfig.is_read_only():
        return
    if os.environ.get(kbconfig.READ_ONLY_ENV) == "1":
        # a server started with KB_READ_ONLY=1 (the shared site) keeps its documented 405 {"error"} on the routes that
        # already refuse themselves; every other write gets the same 405 here
        if request.url.path.rstrip("/").startswith(SELF_REFUSING):
            return
        raise HTTPException(405, kbconfig.READ_ONLY_MESSAGE)
    raise HTTPException(403, kbconfig.READ_ONLY_MESSAGE)


def safe_raw_path(path: str = Path(...)) -> str:
    """Dependency: absolute path of a file under raw/<format>/ for the route param `path`
    (`raw/printed-docs/x.pdf` or `printed-docs/x.pdf`). 404 on traversal, symlink escape, raw/inbox or a
    missing file. Reuses the services' guard (`corpus.check_raw_path`)."""
    rel = path if path.startswith("raw/") else f"raw/{path}"
    full, err = corpus.check_raw_path(rel)
    if err or not full or not os.path.isfile(full):
        raise HTTPException(404, "no such raw file")
    return full


class BodyLimitMiddleware:
    """Pure ASGI: a request body over MAX_BODY_BYTES (MAX_UPLOAD_BYTES on UPLOAD_PATHS) is 413; one without Content-Length is 411."""

    def __init__(self, app, max_bytes=MAX_BODY_BYTES):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in MUTATING:
            headers = dict(scope["headers"])
            length = headers.get(b"content-length")
            if length is None and b"transfer-encoding" in headers:
                return await JSONResponse({"detail": "Content-Length required"}, 411)(scope, receive, send)
            limit = self.max_bytes
            if scope["path"] in UPLOAD_PATHS:
                limit = max(limit, MAX_UPLOAD_BYTES)
            elif scope["path"].startswith(CHAT_UPLOAD_PREFIX):
                limit = max(limit, MAX_CHAT_UPLOAD_BYTES)
            if length is not None and (not length.isdigit() or int(length) > limit):
                return await JSONResponse({"detail": "request body too large"}, 413)(scope, receive, send)
        await self.app(scope, receive, send)
