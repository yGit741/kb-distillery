"""Local-only guards: loopback bind, loopback Origin/Host on mutations, 4 MB body cap, raw path guard.

The API serves a private vault to its owner on this machine. Nothing here is authentication: the rules
keep a web page in another tab (or a DNS-rebinding host name) from driving it.
"""
import ipaddress
import os
from urllib.parse import urlparse

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


# Mutating routes that touch no kb folder, matched whole (a path equals one, or continues after one + "/"): feature flags,
# chat turns and settings (their state lives outside the kb), graph and scope queries that only compute a read, and the
# routes that create a *new* kb elsewhere. Everything else that mutates is refused on a read-only kb, including chat
# sessions, recent steps, attachments and skills (they write under <kb>/.local).
READ_ONLY_OPEN = ("/api/flags", "/api/graph", "/api/scopes/resolve", "/api/chat/answer", "/api/chat/message",
                  "/api/chat/settings", "/api/chat/keys", "/api/kb/import", "/api/kb/inbox")
READ_ONLY_OPEN_EXACT = ("/api/chat",)


def _read_only_open(path: str) -> bool:
    path = path.rstrip("/")
    return path in READ_ONLY_OPEN_EXACT or any(path == p or path.startswith(p + "/") for p in READ_ONLY_OPEN)


def require_writable_kb(request: Request):
    """App-wide dependency. On a read-only kb (example, `[kb] read_only`, $KB_READ_ONLY) every mutation is 403
    unless its route is in `READ_ONLY_OPEN`."""
    if request.method not in MUTATING or _read_only_open(request.url.path):
        return
    if kbconfig.is_read_only():
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
