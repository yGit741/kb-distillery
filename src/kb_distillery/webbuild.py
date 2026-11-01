"""Frontend build helpers that belong to no publisher: the app's sources digest, used to know when `src/kb_distillery/_webapp` is stale."""
import hashlib
from pathlib import Path


def frontend_source_hash(frontend):
    """Digest of what the app bundle is made of: the app sources (not tests), its config and lockfile."""
    frontend = Path(frontend)
    h = hashlib.sha256()
    files = [p for p in (frontend / "src").rglob("*") if p.is_file() and ".test." not in p.name
             and "test" not in p.relative_to(frontend / "src").parts[:1]]
    files += [frontend / n for n in ("index.html", "vite.config.ts", "tsconfig.json", "package.json", "package-lock.json")
              if (frontend / n).is_file()]
    for p in sorted(files):
        h.update(p.relative_to(frontend).as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()
