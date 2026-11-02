"""`create_app()` — the FastAPI application.

Routers are auto-discovered: every module in `kb_distillery.api.routers` that exposes `router` is included, so a new
resource is a new file and nothing shared is edited. The old dashboard page URLs redirect to their React routes
(`PORTED`); anything else no router owns is a 404.
"""
import importlib
import pkgutil

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from kb_distillery.api import security
from kb_distillery.api.spa import spa_router

ROUTERS_PACKAGE = "kb_distillery.api.routers"
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]", "testserver"]
# Old dashboard page URLs, each redirecting to the React route that replaced it (also reached as /legacy/<page>).
PORTED = {
    "/": "/app/system", "/index.html": "/app/system", "/ops": "/app/system",
    "/start": "/app/start", "/start.html": "/app/start",
    "/covector-visualization.html": "/app/covector",
    "/graph": "/app/graph", "/graph.html": "/app/graph",
    "/explore": "/app/pages", "/explore.html": "/app/pages",
    "/scopes": "/app/scopes", "/scopes.html": "/app/scopes",
    "/pipeline": "/app/pipeline", "/digestion": "/app/pipeline", "/digestion.html": "/app/pipeline",
    "/lifecycle": "/app/lifecycle", "/lifecycle.html": "/app/lifecycle",
    "/chat": "/app/chat", "/chat.html": "/app/chat",
}


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


def create_app(routers_package=ROUTERS_PACKAGE, dist=None, allowed_hosts=None) -> FastAPI:
    app = FastAPI(title="Thesis KB API", version="1",
                  dependencies=[Depends(security.require_loopback_origin)])
    app.add_middleware(security.BodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ALLOWED_HOSTS)

    for _name, router in discover_routers(routers_package):
        app.include_router(router)
    app.include_router(spa_router(dist))

    def redirect_to_app(path):
        def go(request: Request):
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(PORTED[path] + query, status_code=307)
        return go

    for old in PORTED:
        for url in (old, "/legacy" + (old if old != "/" else "")):
            app.add_api_route(url, redirect_to_app(old), methods=["GET", "HEAD"], include_in_schema=False)
    return app
