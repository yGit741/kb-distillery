"""Deploy a build directory to a Cloudflare Worker, with guards, rollback and a status file.

    pixi run share -- deploy-main [--force] [--dry-run]   build main (private) → Worker `kb`
    pixi run share -- status                               last deploy outcome (status.json)
    pixi run share -- rollback [--to ID]                   wrangler rollback, then re-check the gate
    pixi run share -- config --google-client-id ID         store the OAuth client id in your share config

`deploy(dir, worker, *, require_access, force=False, message=None)` → DeployResult:

1. **Auth gate** (`require_access`): unauthenticated GET `/` must 302 → `/auth/login`, and
   `/auth/login` must 302 → accounts.google.com, else `refused-no-access`. The very first
   auth-enabled deploy is allowed when the live Worker carries no `kb-share` deploy message
   yet (bootstrap); the gate is re-verified after every auth-enabled deploy.
2. **Never older, never churn**: the live version's deploy message `kb-share <sha> <ver> <profile>`
   gives `live_sha`; same → `skipped-same`; not an ancestor of the new sha → `skipped-older`;
   absent/unparseable → proceed. `force=True` bypasses this guard only.
3. A temp Worker dir (`public/` = the build, `wrangler.jsonc` from `worker/wrangler.template.jsonc`,
   `auth.js` for the private site) is deployed with `npx wrangler@<pinned> deploy --message …`.

One deploy at a time (lock file with pid in CACHE_DIR; a dead pid is reclaimed). The StatusFile
is written on every outcome, exceptions included; everything is logged to LOG_PATH.
Cloudflare calls go through two injectable seams, `runner` (subprocess) and `http` (HEAD/GET
without following redirects), so tests never touch the network.
"""
import argparse
import contextlib
import datetime as _dt
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from kb_distillery.config.resources import resource
from kb_distillery.publish.cloudflare import config as share_config
from kb_distillery.publish.cloudflare import contracts
from kb_distillery.publish.cloudflare.contracts import (ACCOUNT_SUBDOMAIN, CACHE_DIR, DEPLOY_MESSAGE_PREFIX, LOG_PATH, REPO,
                                  STATUS_PATH, WORKER_MAIN, WRANGLER_VERSION, DeployResult, StatusFile)

WORKER_DIR = resource("publish/cloudflare/worker")      # the Cloudflare Worker sources (auth.js, admin.js, wrangler template)
CF_ACCOUNT_ID = os.environ.get("KB_CLOUDFLARE_ACCOUNT_ID") or "7803af2d776eeea4c226f8e594121a10"  # the panel's REST calls (not secret)
WORKER_SCRIPTS = ("auth.js", "admin.js", "flags.gen.js")  # private site: sign-in + panel API + runtime flag names
LOCK_NAME = "deploy.lock"
PENDING_NAME = "pending"
DRY_RUN = "dry-run"  # extra result state for --dry-run; never written to the status file
GATE_TIMEOUT = 20
_MESSAGE_RE = re.compile(rf"^{DEPLOY_MESSAGE_PREFIX} (?P<sha>[0-9a-f]{{7,40}}) (?P<version>\S+) (?P<profile>\S+)$")
_VERSION_ID_RE = re.compile(r"(?:Current Version ID|Version ID): ([0-9a-f-]{36})")


class LockHeld(RuntimeError):
    pass


# ---------- paths (module-level so tests can patch them) ----------

def cache_dir() -> Path:
    return Path(CACHE_DIR)


def lock_path() -> Path:
    return cache_dir() / LOCK_NAME


def pending_path() -> Path:
    return cache_dir() / PENDING_NAME


def status_file() -> StatusFile:
    return StatusFile(Path(STATUS_PATH))


def worker_url(worker: str) -> str:
    return f"https://{worker}.{ACCOUNT_SUBDOMAIN}.workers.dev"


def log(line: str) -> None:
    stamp = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {line}\n")
    except OSError:
        pass


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# ---------- config ----------

def load_config(path: Path = None) -> dict:
    """The share config (`kb_distillery.publish.cloudflare.config`; `path` reads that one file) + env overrides
    → {google_client_id, allowed_emails, compatibility_date, flags_kv_id}."""
    return share_config.settings(path)


def save_config(cfg: dict, path: Path = None) -> Path:
    """Store the client id and allowlist in `path`, else in the config file in use, else in the user file.
    Every other line of the file stays as it is."""
    p = Path(path or share_config.write_path())
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    emails = ", ".join(json.dumps(e) for e in cfg["allowed_emails"])
    text = share_config.set_values(text, "auth", {"google_client_id": json.dumps(cfg["google_client_id"]),
                                                  "allowed_emails": f"[{emails}]"})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---------- Worker dir ----------

def render_wrangler(worker: str, require_access: bool, cfg: dict, spa: bool = False) -> str:
    template = (WORKER_DIR / "wrangler.template.jsonc").read_text(encoding="utf-8")
    if require_access:
        assets = {"directory": "./public", "binding": "ASSETS", "run_worker_first": True}
        variables = {"GOOGLE_CLIENT_ID": cfg["google_client_id"],
                     "ALLOWED_EMAILS": ",".join(cfg["allowed_emails"]),
                     "CF_ACCOUNT_ID": CF_ACCOUNT_ID}
        # global_fetch_strictly_public: the panel (admin.js) fetches snapshot-*.workers.dev manifests,
        # which a same-account Worker otherwise cannot reach (Cloudflare error 1042).
        script = (f'  "main": "auth.js",\n  "vars": {json.dumps(variables)},\n'
                  '  "compatibility_flags": ["global_fetch_strictly_public"],\n')
        if cfg.get("flags_kv_id"):   # runtime flag overrides (admin.js handleFlags); unset → GET {}, PUT 503
            script += f'  "kv_namespaces": [{{"binding": "FLAGS_KV", "id": {json.dumps(cfg["flags_kv_id"])}}}],\n'
    else:
        assets = {"directory": "./public"}
        script = ""
    if spa:      # the React-app layout: client-side routes (/graph, /pages/x) answer with index.html
        assets["not_found_handling"] = "single-page-application"
    return (template.replace("{{name}}", worker)
            .replace("{{compatibility_date}}", cfg["compatibility_date"])
            .replace("{{assets}}", json.dumps(assets))
            .replace("{{script}}", script))


def render_worker_dir(build_dir: Path, worker: str, require_access: bool, cfg: dict, dest: Path) -> Path:
    """`dest/` ← public/ (copy of the build), wrangler.jsonc, auth.js + admin.js when the site is private."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(build_dir, dest / "public")
    spa = Path(build_dir, "manifest.json").is_file() and read_manifest(build_dir).get("layout") == "app"
    (dest / "wrangler.jsonc").write_text(render_wrangler(worker, require_access, cfg, spa=spa), encoding="utf-8")
    if require_access:
        for script in WORKER_SCRIPTS:
            shutil.copy2(WORKER_DIR / script, dest / script)
    return dest


def read_manifest(build_dir: Path) -> dict:
    try:
        return json.loads((Path(build_dir) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"build dir {build_dir} has no readable manifest.json: {e}")


def wrangler_cmd(*args: str) -> list:
    return ["npx", f"wrangler@{WRANGLER_VERSION}", *args]


# ---------- Cloudflare seams ----------

def _default_runner(cmd, cwd=None, timeout=600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _ssl_context():
    """Verify against the OS trust store (truststore) so a corporate TLS proxy's CA is honoured
    the way curl and the browser honour it; fall back to Python's bundle without truststore."""
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def _default_http(url: str) -> tuple:
    """(status, location) of a GET without following redirects; (0, '') when unreachable."""
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_ssl_context()))
    req = urllib.request.Request(url, headers={"Accept": "text/html", "User-Agent": "kb-share-gate"})
    try:
        with opener.open(req, timeout=GATE_TIMEOUT) as res:
            return res.status, res.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", "")
    except (urllib.error.URLError, OSError):
        return 0, ""


def check_gate(worker: str, http: Callable = None) -> Optional[str]:
    """None when the unauthenticated gate holds, else the reason it does not."""
    http = http or _default_http
    base = worker_url(worker)
    status, loc = http(base + "/")
    if status != 302 or not loc.rstrip("/").endswith("/auth/login"):
        return f"GET / → {status or 'unreachable'} {loc or ''}".rstrip() + " (expected 302 → /auth/login)"
    status, loc = http(base + "/auth/login")
    if status != 302 or "accounts.google.com" not in loc:
        return f"GET /auth/login → {status or 'unreachable'} {loc[:60] if loc else ''}".rstrip() + \
            " (expected 302 → accounts.google.com)"
    return None


def parse_message(message: Optional[str]) -> Optional[dict]:
    m = _MESSAGE_RE.match((message or "").strip())
    return m.groupdict() if m else None


def live_message(worker: str, runner: Callable = None) -> Optional[str]:
    """Deploy message of the version currently serving `worker` (None when absent or unreadable)."""
    runner = runner or _default_runner
    try:
        dep = runner(wrangler_cmd("deployments", "list", "--name", worker, "--json"), cwd=str(REPO))
        if dep.returncode != 0:
            return None
        deployments = json.loads(dep.stdout)
        if not deployments:
            return None
        versions = deployments[-1].get("versions") or []
        live = max(versions, key=lambda v: v.get("percentage", 0))["version_id"]
        ver = runner(wrangler_cmd("versions", "list", "--name", worker, "--json"), cwd=str(REPO))
        if ver.returncode != 0:
            return None
        for v in json.loads(ver.stdout):
            if v.get("id") == live:
                return (v.get("annotations") or {}).get("workers/message")
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        return None
    return None


def is_ancestor(old: str, new: str, git_root: Path = REPO) -> Optional[bool]:
    """True/False from git merge-base; None when git cannot decide (unknown object)."""
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", old, new], cwd=str(git_root),
                          capture_output=True, text=True)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


# ---------- lock ----------

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_owner() -> Optional[int]:
    """pid holding the deploy lock, or None (a lock left by a dead pid is reclaimed)."""
    path = lock_path()
    try:
        pid = int(path.read_text().strip() or 0)
    except (OSError, ValueError):
        return None
    if pid and _pid_alive(pid):
        return pid
    with contextlib.suppress(FileNotFoundError):
        path.unlink()
    log(f"reclaimed stale deploy lock (pid {pid})")
    return None


@contextlib.contextmanager
def deploy_lock():
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            owner = lock_owner()
            if owner:
                raise LockHeld(f"another deploy is running (pid {owner})")
            continue
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        try:
            yield
        finally:
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
        return
    raise LockHeld("could not acquire the deploy lock")


# ---------- deploy ----------

def deploy(dir, worker: str, *, require_access: bool, force: bool = False, message: Optional[str] = None,
           dry_run: bool = False, runner: Callable = None, http: Callable = None,
           git_root: Path = REPO, config: dict = None, status_path: Optional[Path] = None) -> DeployResult:
    """`status_path` overrides the status file (snapshots keep theirs apart from the main-site chip)."""
    runner = runner or _default_runner
    http = http or _default_http
    cfg = config or load_config()
    build_dir = Path(dir)
    manifest = read_manifest(build_dir)
    sha, version, profile = manifest.get("content_sha", ""), manifest.get("kb_version", ""), manifest.get("profile", "")
    message = message or f"{DEPLOY_MESSAGE_PREFIX} {sha} {version} {profile}"
    url = worker_url(worker)
    status = StatusFile(Path(status_path)) if status_path else status_file()

    if config is None:          # the config came from files: a clean runner has none, and must not deploy
        try:
            share_config.require()
            share_config.check_deploy(cfg, require_access, ACCOUNT_SUBDOMAIN)
        except share_config.ShareConfigError as e:
            log(f"deploy {worker}: refused — {e}")
            if not dry_run:
                status.write("failed", sha, version, now_iso(), error=str(e), url=url)
            return DeployResult(state="failed", url=url, error=str(e))

    if dry_run:
        dest = render_worker_dir(build_dir, worker, require_access, cfg, cache_dir() / "dry-run" / worker)
        cmd = wrangler_cmd("deploy", "--message", message)
        print(f"dry-run: Worker dir {dest}")
        print(f"dry-run: (cd {dest} && {' '.join(repr(c) if ' ' in c else c for c in cmd)})")
        print((dest / "wrangler.jsonc").read_text(encoding="utf-8"))
        return DeployResult(state=DRY_RUN, url=url, error=None)

    try:
        with deploy_lock():
            status.write("deploying", sha, version, now_iso(), url=url)
            log(f"deploy {worker} ← {message}")
            result = _deploy_locked(build_dir, worker, require_access, force, message, runner, http, git_root, cfg,
                                    sha, version, url)
    except LockHeld as e:
        log(f"deploy {worker}: {e}")
        return DeployResult(state="failed", url=url, error=str(e))  # the running deploy owns the status file
    except Exception as e:  # noqa: BLE001 — every outcome lands in the status file
        result = DeployResult(state="failed", url=url, error=f"{type(e).__name__}: {e}")
    status.write(result.state, sha, version, now_iso(), error=result.error, url=result.url)
    log(f"deploy {worker}: {result.state}" + (f" — {result.error}" if result.error else ""))
    return result


def _deploy_locked(build_dir, worker, require_access, force, message, runner, http, git_root, cfg, sha, version, url):
    live = live_message(worker, runner)
    parsed = parse_message(live)
    if require_access:
        reason = check_gate(worker, http)
        if reason and parsed:
            return DeployResult(state="refused-no-access", url=url, error=f"auth gate down, nothing uploaded: {reason}")
        if reason:
            log(f"bootstrap: live {worker} is not a kb-share deploy yet ({reason}); first auth-enabled deploy allowed")
        if not cfg.get("google_client_id"):
            log("warning: google_client_id is empty — set KB_SHARE_GOOGLE_CLIENT_ID or `share config --google-client-id`")
    if parsed and not force:
        if parsed["sha"] == sha or (len(parsed["sha"]) >= 7 and sha.startswith(parsed["sha"])):
            return DeployResult(state="skipped-same", url=url)
        anc = is_ancestor(parsed["sha"], sha, git_root)
        if anc is False:
            return DeployResult(state="skipped-older", url=url,
                                error=f"live {parsed['sha'][:9]} ({parsed['version']}) is not an ancestor of {sha[:9]}")
        if anc is None:
            log(f"live sha {parsed['sha'][:9]} unknown to git here — proceeding")
    elif parsed and force:
        log(f"force: skipping the ancestor guard (live {parsed['sha'][:9]} {parsed['version']})")

    with tempfile.TemporaryDirectory(prefix="kb-share-") as tmp:
        dest = render_worker_dir(build_dir, worker, require_access, cfg, Path(tmp) / worker)
        proc = runner(wrangler_cmd("deploy", "--message", message), cwd=str(dest))
    if proc.returncode != 0:
        tail = ((proc.stderr or "") + (proc.stdout or "")).strip()[-600:]
        return DeployResult(state="failed", url=url, error=f"wrangler deploy exited {proc.returncode}: {tail}")
    m = _VERSION_ID_RE.search(proc.stdout or "")
    version_id = m.group(1) if m else None
    if require_access:
        reason = check_gate(worker, http)
        if reason:
            return DeployResult(state="failed", url=url, version_id=version_id,
                                error=f"DEPLOYED BUT THE AUTH GATE IS DOWN — the site may be open: {reason}. "
                                      f"Fix the Worker or `share rollback` now")
    return DeployResult(state="deployed", url=url, version_id=version_id)


def rollback(worker: str, to: Optional[str] = None, *, require_access: bool = True,
             runner: Callable = None, http: Callable = None, status_path: Optional[Path] = None) -> DeployResult:
    """`wrangler rollback [version-id]` then re-check the auth gate (`require_access`; False for a public
    snapshot Worker, which has no gate); status file updated (`status_path` keeps a snapshot's apart)."""
    runner = runner or _default_runner
    http = http or _default_http
    url = worker_url(worker)
    status = StatusFile(Path(status_path)) if status_path else status_file()
    try:
        with deploy_lock():
            args = ["rollback", *([to] if to else []), "--name", worker, "--yes", "--message", "kb-share rollback"]
            proc = runner(wrangler_cmd(*args), cwd=str(REPO))
            if proc.returncode != 0:
                tail = ((proc.stderr or "") + (proc.stdout or "")).strip()[-600:]
                result = DeployResult(state="failed", url=url, error=f"wrangler rollback exited {proc.returncode}: {tail}")
            else:
                m = _VERSION_ID_RE.search(proc.stdout or "")
                result = DeployResult(state="deployed", url=url, version_id=m.group(1) if m else to)
                reason = check_gate(worker, http) if require_access else None
                if reason:
                    result = DeployResult(state="failed", url=url, version_id=result.version_id,
                                          error=f"ROLLED BACK BUT THE AUTH GATE IS DOWN — the site may be open: {reason}")
    except LockHeld as e:
        return DeployResult(state="failed", url=url, error=str(e))
    except Exception as e:  # noqa: BLE001
        result = DeployResult(state="failed", url=url, error=f"{type(e).__name__}: {e}")
    live = parse_message(live_message(worker, runner)) or {}
    status.write(result.state, live.get("sha", ""), live.get("version", ""), now_iso(), error=result.error, url=url)
    log(f"rollback {worker}: {result.state}" + (f" — {result.error}" if result.error else ""))
    return result


# ---------- versions upload / deploy (helpers; `deploy()` still uses `wrangler deploy`) ----------

_UPLOAD_ID_RE = re.compile(r"Worker Version ID:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


def upload_version_cmd(message: str, tag: Optional[str] = None) -> list:
    return wrangler_cmd("versions", "upload", "--message", message, *(["--tag", tag] if tag else []))


def parse_upload_output(stdout: str) -> Optional[str]:
    """Version id from `wrangler versions upload` stdout (it has no --json); None when absent."""
    m = _UPLOAD_ID_RE.search(stdout or "")
    return m.group(1) if m else None


def upload_version(dir, message: str, *, tag: Optional[str] = None, runner: Callable = None) -> str:
    """Upload the rendered Worker dir (`wrangler.jsonc` inside) as a new, undeployed Version → its id."""
    runner = runner or _default_runner
    proc = runner(upload_version_cmd(message, tag), cwd=str(dir))
    if proc.returncode != 0:
        tail = ((proc.stderr or "") + (proc.stdout or "")).strip()[-600:]
        raise RuntimeError(f"wrangler versions upload exited {proc.returncode}: {tail}")
    vid = parse_upload_output(proc.stdout)
    if not vid:
        raise RuntimeError(f"wrangler versions upload printed no version id: {(proc.stdout or '').strip()[-300:]}")
    return vid


def deploy_version_cmd(worker: str, version_id: str, pct: int = 100, message: Optional[str] = None) -> list:
    if not 0 < int(pct) <= 100:
        raise ValueError(f"pct must be in 1..100, got {pct}")
    return wrangler_cmd("versions", "deploy", f"{version_id}@{int(pct)}", "--name", worker, "--yes",
                        *(["--message", message] if message else []))


def deploy_version(worker: str, version_id: str, pct: int = 100, *, message: Optional[str] = None,
                   runner: Callable = None) -> None:
    """Route `pct`% of `worker`'s traffic to `version_id` (raises on a non-zero exit)."""
    runner = runner or _default_runner
    proc = runner(deploy_version_cmd(worker, version_id, pct, message), cwd=str(REPO))
    if proc.returncode != 0:
        tail = ((proc.stderr or "") + (proc.stdout or "")).strip()[-600:]
        raise RuntimeError(f"wrangler versions deploy exited {proc.returncode}: {tail}")


def parse_deployments(stdout: str) -> list:
    """`wrangler deployments list --json` → [{id, created_on, message, versions: [(version_id, pct)]}], newest first."""
    try:
        rows = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return []
    out = []
    for d in rows if isinstance(rows, list) else []:
        out.append({"id": d.get("id"), "created_on": d.get("created_on"),
                    "message": (d.get("annotations") or {}).get("workers/message"),
                    "versions": [(v.get("version_id"), v.get("percentage")) for v in d.get("versions") or []]})
    return sorted(out, key=lambda d: d["created_on"] or "", reverse=True)


# ---------- CLI ----------

def deploy_main(force: bool = False, dry_run: bool = False, build_dir=None, **seams) -> DeployResult:
    """Build main (private profile) and deploy it to the live Worker; `build_dir` skips the build."""
    status = status_file()
    if build_dir is None:
        try:
            from kb_distillery.publish.site.build import build
            build_dir = build("main", profile="private").dir
        except Exception as e:  # noqa: BLE001
            status.write("failed", "", "", now_iso(), error=f"build failed: {type(e).__name__}: {e}",
                         url=worker_url(WORKER_MAIN))
            log(f"deploy-main: build failed — {type(e).__name__}: {e}")
            return DeployResult(state="failed", url=worker_url(WORKER_MAIN), error=f"build failed: {e}")
    return deploy(build_dir, WORKER_MAIN, require_access=True, force=force, dry_run=dry_run, **seams)


def cmd_deploy_main(args) -> int:
    if lock_owner():
        pending_path().parent.mkdir(parents=True, exist_ok=True)
        pending_path().touch()
        print("another deploy is running — marked pending, it will rerun once")
        return 0
    result = deploy_main(force=args.force, dry_run=args.dry_run, build_dir=getattr(args, "dir", None))
    print(_describe(result))
    if not args.dry_run and pending_path().exists():  # debounce: triggers that arrived meanwhile → one rerun
        pending_path().unlink()
        log("pending trigger found — rerunning deploy-main once")
        result = deploy_main(force=args.force)
        print(_describe(result))
    return deploy_main_exit_code(result.state)


# A skip is a guard doing its job, not an error: the Mac (autodeploy) and the GitHub backstop
# (.github/workflows/deploy-main.yml) both call deploy-main for the same sha, so `skipped-same`
# and `skipped-older` must exit 0 or every CI run after a Mac deploy would be red.
OK_STATES = ("deployed", "skipped-same", "skipped-older", DRY_RUN)


def deploy_main_exit_code(state: str) -> int:
    return 0 if state in OK_STATES else 1


def _describe(r: DeployResult) -> str:
    bits = [r.state, r.url or ""]
    if r.version_id:
        bits.append(f"version {r.version_id}")
    if r.error:
        bits.append(f"— {r.error}")
    return " ".join(b for b in bits if b)


def cmd_status(args) -> int:
    data = status_file().read()
    if not data:
        print("no deploy recorded yet")
        return 0
    age = ""
    try:
        at = _dt.datetime.fromisoformat(data["at"])
        age = f" ({int((_dt.datetime.now(_dt.timezone.utc) - at).total_seconds() // 60)} min ago)"
    except (TypeError, ValueError):
        pass
    print(f"{data['state']}  kb-{data['kb_version'] or '?'}  {(data['sha'] or '')[:9]}  {data['at']}{age}")
    if data.get("url"):
        print(f"url: {data['url']}")
    if data.get("error"):
        print(f"error: {data['error']}")
    print(f"log: {LOG_PATH}")
    return 0 if data["state"] != "failed" else 1


def rollback_target(worker: str) -> tuple:
    """(full worker name, require_access, status_path) for `--worker`: `kb` → the gated main site;
    a snapshot (full name or bare name) → public, its own status file. Raises ValueError otherwise."""
    from kb_distillery.publish.site import snapshots
    worker = (worker or "").strip()
    if worker == WORKER_MAIN:
        return WORKER_MAIN, True, None
    if not snapshots.parse_worker(worker):
        matches = snapshots.resolve_target(worker)
        if len(matches) > 1:
            raise ValueError(f"{worker!r} is ambiguous — give the full worker name: "
                             + ", ".join(s["name"] for s in matches))
        if not matches:
            raise ValueError(f"{worker!r} is neither {WORKER_MAIN} nor a snapshot-* Worker of ours")
        worker = matches[0]["name"]
    return worker, False, Path(CACHE_DIR) / f"status-{worker}.json"


def cmd_rollback(args) -> int:
    try:
        worker, require_access, status_path = rollback_target(args.worker)
    except ValueError as e:
        print(f"rollback: {e}")
        return 1
    result = rollback(worker, args.to, require_access=require_access, status_path=status_path)
    print(_describe(result))
    if result.state == "deployed" and not require_access:
        print(f"{worker} is public again at its previous content; `share history {worker}` shows what is live")
    return 0 if result.state == "deployed" else 1


def cmd_config(args) -> int:
    cfg = load_config()
    if args.google_client_id is not None or args.allowed_emails:
        # store only what the file holds plus what was passed: env overrides in `cfg` never reach the file
        auth = share_config.load().get("auth") or {}
        stored = {"google_client_id": auth.get("google_client_id") or "", "allowed_emails": list(auth.get("allowed_emails") or [])}
        if args.google_client_id is not None:
            stored["google_client_id"] = cfg["google_client_id"] = args.google_client_id.strip()
        if args.allowed_emails:
            stored["allowed_emails"] = cfg["allowed_emails"] = [e.strip() for e in args.allowed_emails.split(",") if e.strip()]
        print(f"wrote {save_config(stored)}")
    print(json.dumps(cfg, indent=2))
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("deploy-main", help="build main and deploy it to the private `kb` Worker")
    p.add_argument("--force", action="store_true", help="skip the same/older guard (manual use only)")
    p.add_argument("--dry-run", action="store_true", help="render the Worker dir and print the wrangler command")
    p.add_argument("--dir", default=None, help="deploy an existing build dir (index.html + manifest.json) instead of building")
    p.add_argument("--app", action="store_true", help=argparse.SUPPRESS)      # the only layout; accepted for old scripts
    p.set_defaults(func=cmd_deploy_main)
    s = subparsers.add_parser("status", help="last deploy outcome")
    s.set_defaults(func=cmd_status)
    r = subparsers.add_parser("rollback", help="previous version of kb (then the auth gate is re-checked) or of a snapshot")
    r.add_argument("--to", default=None, help="version id to roll back to (default: previous); `share history` lists them")
    r.add_argument("--worker", default=WORKER_MAIN, help="kb (default) or a snapshot: bare name or snapshot-<date>-<name>")
    r.set_defaults(func=cmd_rollback)
    c = subparsers.add_parser("config", help="show or store share.toml values (Google client id, allowlist)")
    c.add_argument("--google-client-id", default=None)
    c.add_argument("--allowed-emails", default=None, help="comma-separated")
    c.set_defaults(func=cmd_config)
