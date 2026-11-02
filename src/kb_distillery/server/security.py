"""Local-only guards: loopback bind, loopback Origin/Host on mutations, 4 MB body cap, raw path guard.

The API serves a private vault to its owner on this machine. Nothing here is authentication: the rules
keep a web page in another tab (or a DNS-rebinding host name) from driving it.
"""
import ipaddress
import os
from urllib.parse import urlparse

from fastapi import HTTPException, Path, Request
from starlette.responses import JSONResponse

from kb_distillery.services import corpus

MAX_BODY_BYTES = 4 * 1024 * 1024
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
    """Refuse to listen on anything but a loopback address (the API has no authentication)."""
    if not is_loopback_host(host):
        raise SystemExit(f"refusing to bind {host!r}: the API is local-only (use 127.0.0.1 or ::1)")


def require_loopback_origin(request: Request):
    """App-wide dependency. A mutating request must carry a loopback Origin (browsers always send one on
    POST); a foreign or missing Origin is refused."""
    if request.method not in MUTATING:
        return
    origin = request.headers.get("origin")
    if origin is None or not is_loopback_host(urlparse(origin).hostname):
        raise HTTPException(403, "cross-origin or origin-less mutation refused")


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
    """Pure ASGI: a request body over MAX_BODY_BYTES is 413; a body without Content-Length is 411."""

    def __init__(self, app, max_bytes=MAX_BODY_BYTES):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in MUTATING:
            headers = dict(scope["headers"])
            length = headers.get(b"content-length")
            if length is None and b"transfer-encoding" in headers:
                return await JSONResponse({"detail": "Content-Length required"}, 411)(scope, receive, send)
            if length is not None and (not length.isdigit() or int(length) > self.max_bytes):
                return await JSONResponse({"detail": "request body too large"}, 413)(scope, receive, send)
        await self.app(scope, receive, send)
