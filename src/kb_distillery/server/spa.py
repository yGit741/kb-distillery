"""The React shell (`src/kb_distillery/_webapp`, build output — never committed) under /app, with SPA fallback to index.html."""
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from kb_distillery.config.resources import repo_root, resource
from kb_distillery.config.paths import vault_root

STAMP = ".src-hash"


def frontend_dir() -> str | None:
    """The `web/` sources (code, not vault content): only in a checkout, None for an installed package."""
    root = repo_root()
    return str(root / "web") if root else None


def dist_dir() -> str:
    """The built shell, `src/kb_distillery/_webapp` (vite builds there, web/vite.config.ts; a wheel ships it)."""
    return str(resource("_webapp"))


def _try_prebuilt(dist, want):
    """Fetch the release's prebuilt bundle into `dist`; True when it is usable for sources hashing to `want` (or None)."""
    from kb_distillery.webbuild import bundle_enabled, bundle_matches_sources, fetch_prebuilt, installed_version

    if not bundle_enabled():
        return False
    if not fetch_prebuilt(installed_version(), dist):
        print("frontend: no prebuilt bundle for this version, building locally", flush=True)
        return False
    if want is not None and not bundle_matches_sources(dist, want):
        print("frontend: web/ differs from the prebuilt bundle, building locally", flush=True)
        return False
    if want is not None:
        (Path(dist) / STAMP).write_text(want + "\n")
    return True


def ensure_app_dist(frontend=None, runner=None, dist=None):
    """Build `src/kb_distillery/_webapp` from the current sources when they changed since the last build.

    When the dist is missing or stale, the release's prebuilt bundle is tried first (`webbuild.fetch_prebuilt`, skipped
    with `KB_WEB_BUNDLE=0`; only for the real `_webapp`, i.e. when `dist` is not passed). It is kept unless its
    `SOURCE_HASH` differs from this checkout's `web/` hash, in which case (a dev checkout) the local build runs.

    Returns "fresh", "built" or a warning string; a failed or impossible build keeps the old dist. An installed
    package has no sources to build from: it serves the bundled shell as it is."""
    from kb_distillery.webbuild import frontend_source_hash

    frontend = frontend or frontend_dir()
    prebuilt = dist is None
    dist = Path(dist or dist_dir())
    if frontend is None:
        if not (dist / "index.html").is_file() and prebuilt and _try_prebuilt(dist, None):
            return "fetched"
        return "fresh" if (dist / "index.html").is_file() else "no bundled web app in this install (build it from a checkout)"
    frontend = Path(frontend)
    want = frontend_source_hash(frontend)
    stamp = dist / STAMP
    if (dist / "index.html").is_file() and stamp.is_file() and stamp.read_text().strip() == want:
        return "fresh"
    if prebuilt and _try_prebuilt(dist, want):
        return "fetched"
    run = runner or subprocess.run
    if not (frontend / "node_modules").is_dir():
        # a fresh clone has no node_modules: install them once (same as `pixi run web-install`, needs the network)
        print("frontend: installing dependencies (first run only)…", flush=True)
        got = run(["npm", "ci", "--prefix", str(frontend)], capture_output=True, text=True, check=False)
        if got.returncode != 0:
            tail = (got.stderr or got.stdout or "").strip().splitlines()[-6:]
            return ("frontend dependencies could not be installed (needs network and node; or run "
                    "`pixi run web-install` yourself):\n" + "\n".join(tail))
    proc = run(["npm", "run", "build", "--prefix", str(frontend)], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        return "frontend build failed (serving the previous dist):\n" + "\n".join(tail)
    stamp.write_text(want + "\n")
    return "built"


# The shell (index.html) names the hashed bundle, so it must be revalidated on every load (it is under 1 KB, so a
# plain re-fetch is cheap); without a Cache-Control the browser caches it heuristically and keeps running a rebuilt
# app's old bundle.
# Files under assets/ carry a content hash in their name, so a name never changes meaning: cache them for good.
NO_CACHE = "no-cache"
IMMUTABLE = "public, max-age=31536000, immutable"


def _cache_for(full, assets_dir):
    return {"Cache-Control": IMMUTABLE if full.startswith(os.path.realpath(assets_dir) + os.sep) else NO_CACHE}


def spa_router(dist=None) -> APIRouter:
    dist = os.path.realpath(dist or dist_dir())
    router = APIRouter(include_in_schema=False)

    assets_dir = os.path.join(dist, "assets")

    def serve(rel):
        full = os.path.realpath(os.path.join(dist, rel))
        if rel and full.startswith(dist + os.sep) and os.path.isfile(full) and not os.path.basename(full).startswith("."):
            return FileResponse(full, headers=_cache_for(full, assets_dir))
        index = os.path.join(dist, "index.html")
        if not os.path.isfile(index):
            raise HTTPException(404, "src/kb_distillery/_webapp is not built (pixi run web-build)")
        return FileResponse(index, headers={"Cache-Control": NO_CACHE})

    @router.get("/app")
    @router.get("/app/{path:path}")
    def app_shell(path: str = ""):
        return serve(path)

    @router.get("/assets/{path:path}")      # the built index.html references /assets/* (vite base "/")
    def assets(path: str):
        full = os.path.realpath(os.path.join(dist, "assets", path))
        if not full.startswith(os.path.join(dist, "assets") + os.sep) or not os.path.isfile(full):
            raise HTTPException(404)
        return FileResponse(full, headers=_cache_for(full, assets_dir))

    return router
