"""`create_app()` — the FastAPI application.

Routers are auto-discovered: every module in `kb.api.routers` that exposes `router` is included, so a new
resource is a new file and nothing shared is edited. Anything no router owns falls through to the legacy
stdlib dashboard (`legacy.py`) until its screen is ported.
"""
import importlib
import pkgutil
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from kb.api import security
from kb.api.legacy import LegacyBridge
from kb.api.spa import spa_router

ROUTERS_PACKAGE = "kb.api.routers"
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]", "testserver"]
# Legacy pages whose screen is ported: the old path redirects to the app (the old page stays at /legacy/...).
PORTED = {"/graph": "/app/graph", "/graph.html": "/app/graph"}
LEGACY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def discover_routers(package=ROUTERS_PACKAGE):
    """Yield (module name, APIRouter) for each public module of `package` that exposes `router`."""
    pkg = importlib.import_module(package)
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package}.{info.name}")
        router = getattr(module, "router", None)
        if router is not None:
            yield info.name, router


def create_app(routers_package=ROUTERS_PACKAGE, dist=None, legacy=True, allowed_hosts=None) -> FastAPI:
    bridge = LegacyBridge()

    @asynccontextmanager
    async def lifespan(_app):
        yield
        await bridge.close()

    app = FastAPI(title="Thesis KB API", version="1", lifespan=lifespan,
                  dependencies=[Depends(security.require_loopback_origin)])
    app.state.legacy = bridge
    app.add_middleware(security.BodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ALLOWED_HOSTS)

    for _name, router in discover_routers(routers_package):
        app.include_router(router)
    app.include_router(spa_router(dist))

    @app.api_route("/graph", methods=["GET", "HEAD"], include_in_schema=False)
    @app.api_route("/graph.html", methods=["GET", "HEAD"], include_in_schema=False)
    async def ported(request: Request):
        target = PORTED[request.url.path]
        return RedirectResponse(target + (f"?{request.url.query}" if request.url.query else ""), status_code=307)

    if legacy:
        @app.api_route("/legacy/{path:path}", methods=LEGACY_METHODS, name=security.LEGACY_ROUTE,
                       include_in_schema=False)
        async def legacy_prefixed(request: Request, path: str):   # the shell links unported tabs here
            return await bridge.forward(request, "/" + path)

        @app.api_route("/{path:path}", methods=LEGACY_METHODS, name=security.LEGACY_ROUTE,
                       include_in_schema=False)
        async def legacy_catch_all(request: Request, path: str):
            return await bridge.forward(request)
    return app
