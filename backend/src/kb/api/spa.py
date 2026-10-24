"""The React shell (`frontend/dist`, build output — never committed) under /app, with SPA fallback to index.html."""
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from kb.paths import vault_root

FRONTEND = os.path.join(vault_root(), "frontend")
DIST = os.path.join(FRONTEND, "dist")
STAMP = ".src-hash"


def ensure_app_dist(frontend=FRONTEND, runner=None):
    """Build `frontend/dist` from the current sources when they changed since the last build.

    Returns "fresh", "built" or a warning string; a failed or impossible build keeps the old dist."""
    from kb.share.build import frontend_source_hash

    frontend = Path(frontend)
    dist = frontend / "dist"
    want = frontend_source_hash(frontend)
    stamp = dist / STAMP
    if (dist / "index.html").is_file() and stamp.is_file() and stamp.read_text().strip() == want:
        return "fresh"
    if not (frontend / "node_modules").is_dir():
        return "frontend/node_modules is missing — run `pixi run web-install` once, then restart"
    proc = (runner or subprocess.run)(["npm", "run", "build", "--prefix", str(frontend)],
                                      capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        return "frontend build failed (serving the previous dist):\n" + "\n".join(tail)
    stamp.write_text(want + "\n")
    return "built"


def spa_router(dist=None) -> APIRouter:
    dist = os.path.realpath(dist or DIST)
    router = APIRouter(include_in_schema=False)

    def serve(rel):
        full = os.path.realpath(os.path.join(dist, rel))
        if rel and full.startswith(dist + os.sep) and os.path.isfile(full) and not os.path.basename(full).startswith("."):
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
