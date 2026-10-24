"""The React shell (`frontend/dist`, committed) under /app, with SPA fallback to index.html."""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from kb.paths import vault_root

DIST = os.path.join(vault_root(), "frontend", "dist")


def spa_router(dist=None) -> APIRouter:
    dist = os.path.realpath(dist or DIST)
    router = APIRouter(include_in_schema=False)

    def serve(rel):
        full = os.path.realpath(os.path.join(dist, rel))
        if rel and full.startswith(dist + os.sep) and os.path.isfile(full):
            return FileResponse(full)
        index = os.path.join(dist, "index.html")
        if not os.path.isfile(index):
            raise HTTPException(404, "frontend/dist is not built (pixi run web-build)")
        return FileResponse(index)

    @router.get("/app")
    @router.get("/app/{path:path}")
    def app_shell(path: str = ""):
        return serve(path)

    @router.get("/assets/{path:path}")      # the built index.html references /assets/* (vite base "/")
    def assets(path: str):
        full = os.path.realpath(os.path.join(dist, "assets", path))
        if not full.startswith(os.path.join(dist, "assets") + os.sep) or not os.path.isfile(full):
            raise HTTPException(404)
        return FileResponse(full)

    return router
