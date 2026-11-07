"""Frontend build helpers that belong to no publisher: the app's sources digest, used to know when `src/kb_distillery/_webapp` is stale,
and the prebuilt bundle a release carries so a fresh clone does not have to build the React app."""
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

BUNDLE_VERSION_FILE = "BUNDLE_VERSION"
SOURCE_HASH_FILE = "SOURCE_HASH"        # written by the web-bundle workflow: frontend_source_hash of the sources it built
_TIMEOUT = 30


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


def bundle_enabled():
    """`KB_WEB_BUNDLE=0` turns the prebuilt-bundle fetch off (always build locally)."""
    return os.environ.get("KB_WEB_BUNDLE", "1").strip() != "0"


def installed_version():
    """The engine version: the installed distribution's, else the checkout's pyproject.toml; None when neither is known."""
    try:
        from importlib.metadata import version
        return version("kb-distillery")
    except Exception:
        pass
    try:
        text = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
        return m.group(1) if m else None
    except OSError:
        return None


def default_repo():
    """`owner/name` from `$KB_WEB_BUNDLE_REPO`, else from the origin remote of the checkout; None when unknown."""
    env = os.environ.get("KB_WEB_BUNDLE_REPO", "").strip()
    if env:
        return env
    try:
        out = subprocess.run(["git", "-C", str(Path(__file__).resolve().parent), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", out)
    return m.group(1) if m else None


def _get(url):
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:       # noqa: S310 - https (or file:// in tests)
        return r.read()


def _safe_extract(archive, into):
    with tarfile.open(archive, "r:gz") as tf:
        root = os.path.realpath(into)
        for m in tf.getmembers():
            target = os.path.realpath(os.path.join(root, m.name))
            if not (target == root or target.startswith(root + os.sep)) or not (m.isreg() or m.isdir()):
                raise ValueError(f"unsafe member {m.name!r}")
        try:
            tf.extractall(into, filter="data")
        except TypeError:          # python without extraction filters
            tf.extractall(into)


def fetch_prebuilt(version, dest, *, repo=None, url=None, accept=None):
    """Download the release's web bundle for `version` and unpack it into `dest` (the `_webapp` dir). True on success.

    Fetches `webapp-<version>.tar.gz` and `webapp-<version>.sha256` from the GitHub release `v<version>` of `repo`
    (default: `default_repo()`), or from the directory-like base `url` (tests). The sha256 must match; the archive is
    unpacked into a temp dir next to `dest` and renamed into place, so `dest` is never half-written. Marks the result
    with `BUNDLE_VERSION`. Any problem (no release, no network, bad checksum, bad archive) returns False and leaves
    `dest` untouched; it never raises. `accept(dir)`, when given, sees the unpacked bundle before it replaces `dest` and
    may veto it (False).
    """
    dest = Path(dest)
    tmp = None
    try:
        if not version:
            return False
        if url is None:
            repo = repo or default_repo()
            if not repo:
                return False
            url = f"https://github.com/{repo}/releases/download/v{version}"
        base = url.rstrip("/")
        name = f"webapp-{version}"
        blob = _get(f"{base}/{name}.tar.gz")
        want = _get(f"{base}/{name}.sha256").decode("utf-8", "replace").split()
        if not want or hashlib.sha256(blob).hexdigest() != want[0].lower():
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".{dest.name}.new-", dir=dest.parent))
        archive = tmp / "bundle.tar.gz"
        archive.write_bytes(blob)
        out = tmp / "out"
        out.mkdir()
        _safe_extract(archive, out)
        if not (out / "index.html").is_file():
            return False
        if accept is not None and not accept(out):
            return False
        (out / BUNDLE_VERSION_FILE).write_text(version + "\n", encoding="utf-8")
        old = None
        if dest.exists():
            old = tmp / "old"
            os.replace(dest, old)
        try:
            os.replace(out, dest)
        except OSError:
            if old is not None:
                os.replace(old, dest)
            raise
        return True
    except Exception:
        return False
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def bundle_matches_sources(dest, want_hash):
    """Whether a fetched bundle may be used with the local sources: only when its recorded `SOURCE_HASH` equals
    `want_hash` (a dev checkout whose `web/` changed since the release keeps building locally)."""
    f = Path(dest) / SOURCE_HASH_FILE
    if not f.is_file():
        return False        # an unlabelled bundle cannot be shown to match the sources
    return f.read_text(encoding="utf-8").strip() == want_hash
