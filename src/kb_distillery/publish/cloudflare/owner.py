"""The single deploy owner of the private site (Worker `kb`): one process builds and deploys main.

    python -m kb_distillery.publish.cloudflare.owner run      long-lived loop (launchd: examples/launchd/com.kb-distillery.deploy-owner.plist)
    python -m kb_distillery.publish.cloudflare.owner once     one cycle now, then exit (same lock; the user's manual kick)
    python -m kb_distillery.publish.cloudflare.owner status   per-sha state from .cache/share/owner.json
    python -m kb_distillery.publish.cloudflare.owner fresh    exit 0 when a deploy succeeded in the last --hours (CI fallback gate)

Everything else only **nudges** it: `nudge(reason)` touches `.cache/share/wake` (ops commits, ship merge,
the nightly sync). The loop wakes on that touch or every POLL_SECONDS and runs one cycle:

1. `git fetch origin main` → sha. Already handled (deployed / rolled-back / failed for good) → nothing.
2. Build once per sha into `.cache/share/build/<sha>` (kept across cycles; reused if its manifest is there).
3. Remember the live version id, `wrangler versions upload` → `versions deploy <id>@100`.
4. Health: the auth gate (`check_gate`), `/app` answers (200, or 302 → /auth/login when signed out),
   and the live deployment is the uploaded version (its message carries the built sha).
5. Unhealthy → `versions deploy <previous>@100` and a `rolled-back` event; healthy → `deployed` event on
   the merged PR (`… (#N)` subject of the sha) and its round issue.

Network errors (fetch failed, ECONNRESET, ETIMEDOUT, proxy/CONNECT, 5xx) are retried after 10 s / 60 s /
300 s; anything else fails fast. One owner at a time (flock on `.cache/share/owner.lock`); the legacy
deploy lock is held around upload+deploy so a direct `deploy-main` (KB_SHARE_DIRECT=1) cannot interleave.
Seams (`runner`, `http`, `sleep`, `git`, `builder`, `poster`) keep tests off the network.
"""
import argparse
import contextlib
import datetime as _dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from kb_distillery.config.resources import resource
from kb_distillery.publish.cloudflare import deploy as dp
from kb_distillery.publish.cloudflare.contracts import CACHE_DIR, DEPLOY_MESSAGE_PREFIX, REPO, WORKER_MAIN

POLL_SECONDS = 300
TICK_SECONDS = 2
BACKOFF = (10, 60, 300)
MAX_CYCLES = 3            # a sha whose network retries all failed is tried again on up to 3 cycles
KEEP_BUILDS = 3
TERMINAL = ("deployed", "rolled-back", "failed", "rollback-failed", "superseded")
PENDING = ("building", "uploading", "deploying", "failed-network", "failed-module")
CODE_DIR = Path(__file__).resolve().parent           # src/kb_distillery/publish/cloudflare
SITE_DIR = CODE_DIR.parent / "site"                  # src/kb_distillery/publish/site (the builder the owner runs)
CODE_JS = resource("publish/cloudflare/worker")      # the Worker modules (*.js), package data
_MODULE_RE = re.compile(r"Could not resolve|Cannot find module|No such module|ERR_MODULE_NOT_FOUND", re.I)
SETTLE_SECONDS = 15

_NETWORK_RE = re.compile(
    r"fetch failed|ECONNRESET|ETIMEDOUT|ECONNREFUSED|EAI_AGAIN|ENOTFOUND|socket hang up|"
    r"CONNECT tunnel|tunneling socket|proxy|Could not resolve host|Connection (?:reset|refused|timed out)|"
    r"timed out|Temporary failure in name resolution|Network is unreachable|"
    r"\b5\d\d\b (?:Internal|Bad Gateway|Service Unavailable|Gateway Time)|status(?: code)?:? 5\d\d|HTTP 5\d\d|"
    # wrangler words a Cloudflare API 5xx the other way round, then as an "unknown error" with code 10013
    r"(?:Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout) 5\d\d|An unknown error has occurred|code: 10013",
    re.I)


TLS_REASON = "TLS: proxy CA missing in launchd env — rerun pixi run install-deploy-owner from your normal shell"
_TLS_RE = re.compile(
    r"corporate proxy or VPN|certificate mismatch|UNABLE_TO_GET_ISSUER_CERT|SELF_SIGNED_CERT_IN_CHAIN|"
    r"unable to (?:get local issuer|verify the first) certificate|CERTIFICATE_VERIFY_FAILED|self[- ]signed certificate",
    re.I)


def tls_reason(exc_or_text) -> Optional[str]:
    """TLS_REASON when the failure looks like a missing proxy root CA (wrangler/node/git under launchd)."""
    return TLS_REASON if _TLS_RE.search(str(exc_or_text)) else None


def describe(exc) -> str:
    """Error text for state/status: the TLS reason up front when it applies."""
    reason = tls_reason(exc)
    return f"{reason}; {str(exc)[-300:]}" if reason else str(exc)


class NetworkError(RuntimeError):
    """A failure worth retrying."""


def is_network_error(exc_or_text) -> bool:
    if isinstance(exc_or_text, (NetworkError, TimeoutError, ConnectionError, subprocess.TimeoutExpired)):
        return True
    return bool(_NETWORK_RE.search(str(exc_or_text)) or _TLS_RE.search(str(exc_or_text)))


def is_module_error(exc_or_text) -> bool:
    """A build that could not resolve a worker module: usually this process runs stale code (see code_hash)."""
    return bool(_MODULE_RE.search(str(exc_or_text)))


def code_hash(dirs=None) -> str:
    """Hash of the owner's own code on disk (publish/cloudflare/*.py, publish/site/*.py, worker/*.js); a change means restart before building."""
    import hashlib
    h = hashlib.sha256()
    for d, pat in dirs or ((CODE_DIR, "*.py"), (SITE_DIR, "*.py"), (CODE_JS, "*.js")):
        for f in sorted(Path(d).glob(pat)):
            try:
                h.update(f.name.encode() + b"\0" + f.read_bytes())
            except OSError:
                continue
    return h.hexdigest()


def supersede(state, live_sha) -> int:
    """Pending entries other than the live sha are older (the owner deploys the tip): mark them superseded."""
    n = 0
    for s, e in (state.get("shas") or {}).items():
        if s != live_sha and isinstance(e, dict) and e.get("state") in PENDING:
            e.update(state="superseded", superseded_by=live_sha)
            n += 1
    return n


def retry(fn: Callable, *, what: str, sleep: Callable = time.sleep, backoff=BACKOFF):
    """fn() with retries on network errors only (len(backoff) retries); re-raises the last error."""
    for i in range(len(backoff) + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if not is_network_error(e) or i == len(backoff):
                raise
            dp.log(f"owner: {what} — network error, retry in {backoff[i]}s: {str(e)[-200:]}")
            sleep(backoff[i])


# ---------- paths + state ----------

def primary_root(root) -> Path:
    """The primary checkout of `root` (a linked worktree nudges the owner of its primary)."""
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=str(root),
                                capture_output=True, text=True, timeout=10).stdout.strip()
        if common.endswith("/.git"):
            return Path(common).parent
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(root)


def cache(root=None) -> Path:
    return Path(root) / ".cache" / "share" if root else Path(CACHE_DIR)


def wake_path(root=None) -> Path:
    return cache(root) / "wake"


def lock_file(root=None) -> Path:
    return cache(root) / "owner.lock"


def state_path(root=None) -> Path:
    return Path(os.environ.get("KB_SHARE_OWNER_STATUS") or cache(root) / "owner.json")


def build_root(root=None) -> Path:
    return cache(root) / "build"


def load_state(root=None) -> dict:
    try:
        data = json.loads(state_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict, root=None) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".owner-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def _record(doc, sha, root=None, **kv):
    shas = doc.setdefault("shas", {})
    entry = shas.setdefault(sha, {})
    entry.update(kv, at=dp.now_iso())
    if len(shas) > 50:  # newest 50 by time
        for old in sorted(shas, key=lambda s: shas[s].get("at", ""))[:-50]:
            shas.pop(old)
    save_state(doc, root)
    return entry


def nudge(reason: str = "", root=None) -> str:
    """Wake the owner (touch `.cache/share/wake`). Never raises. Returns disabled | nudged | error."""
    try:
        from kb_distillery.publish.cloudflare.autodeploy import enabled
        if not enabled(root or REPO):  # KB_SHARE_AUTODEPLOY=0, or not a share-capable repo
            return "disabled"
        path = wake_path(primary_root(root or REPO))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{dp.now_iso()} {reason}\n", encoding="utf-8")
        return "nudged"
    except Exception as e:  # noqa: BLE001 — a nudge must never break a commit
        print(f"note: deploy owner not nudged — {e}")
        return "error"


@contextlib.contextmanager
def single_instance(root=None):
    """flock(LOCK_EX|LOCK_NB) on owner.lock; raises dp.LockHeld when another owner runs."""
    path = lock_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise dp.LockHeld("another deploy owner is running")
        f.seek(0)
        f.truncate()
        f.write(str(os.getpid()))
        f.flush()
        yield
    finally:
        f.close()  # releases the flock


# ---------- default seams ----------

def _git(args, root) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=120)


def fetch_main(root, git=_git) -> str:
    proc = git(["fetch", "-q", "origin", "main"], root)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise (NetworkError if is_network_error(err) else RuntimeError)(f"git fetch origin main: {err[-300:]}")
    return git(["rev-parse", "origin/main"], root).stdout.strip()


def pr_of(sha, root, git=_git) -> Optional[int]:
    """The PR merged by `sha` (subject `… (#N)`); None for kb() commits and anything else."""
    subject = git(["log", "-1", "--format=%s", sha], root).stdout.strip()
    m = re.search(r"\(#(\d+)\)$", subject)
    return int(m.group(1)) if m else None


def _default_builder(sha, out_root):
    from kb_distillery.publish.site.build import build
    return build(sha, sha, profile="private", out_root=out_root, label=sha).dir


def _default_poster(pr, event, sha, root, **kv):
    """`event` on PR `pr` and on its round issue (feature = head branch minus `infra/`). Never raises."""
    from kb_distillery.git import events, rounds
    events.post(pr, event, sha, root=root, **kv)
    try:
        cp = events._gh(["pr", "view", str(pr), "--json", "body,headRefName"], root)
        info = json.loads(cp.stdout) if cp.returncode == 0 else {}
        round_no = rounds.round_from_pr_body(info.get("body"))
        feature = (info.get("headRefName") or "").removeprefix("infra/")
        if round_no:
            rounds.on_event(round_no, feature, event, sha, pr=pr, root=root, **kv)
    except Exception as e:  # noqa: BLE001
        print(f"note: round event not posted — {e}")


# ---------- cycle ----------

def live_version_id(runner) -> Optional[str]:
    proc = runner(dp.wrangler_cmd("deployments", "list", "--name", WORKER_MAIN, "--json"), cwd=str(REPO))
    if proc.returncode != 0:
        err = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise (NetworkError if is_network_error(err) else RuntimeError)(f"wrangler deployments list: {err[-300:]}")
    rows = dp.parse_deployments(proc.stdout)
    if not rows or not rows[0]["versions"]:
        return None
    return max(rows[0]["versions"], key=lambda v: v[1] or 0)[0]


def health(version_id, sha, *, runner, http) -> Optional[str]:
    """None when healthy, else the reason."""
    reason = dp.check_gate(WORKER_MAIN, http)
    if reason:
        return f"auth gate: {reason}"
    status, loc = http(dp.worker_url(WORKER_MAIN) + "/app")
    if not (status == 200 or (status == 302 and loc.rstrip("/").endswith("/auth/login"))):
        return f"GET /app → {status or 'unreachable'} {loc or ''}".rstrip()
    live = live_version_id(runner)
    if live != version_id:
        return f"live version is {live}, expected the uploaded {version_id}"
    parsed = dp.parse_message(dp.live_message(WORKER_MAIN, runner)) or {}
    if parsed.get("sha") and not sha.startswith(parsed["sha"]):
        return f"live deploy message carries {parsed['sha'][:9]}, built {sha[:9]}"
    return None


def _wrangler_ok(proc, what):
    if proc.returncode != 0:
        err = ((proc.stderr or "") + (proc.stdout or "")).strip()
        raise (NetworkError if is_network_error(err) else RuntimeError)(f"{what} exited {proc.returncode}: {err[-400:]}")
    return proc


def _prune_builds(root, keep_sha):
    base = build_root(root)
    dirs = sorted((d for d in base.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime) if base.is_dir() else []
    for d in dirs[:-KEEP_BUILDS]:
        if d.name != keep_sha:
            shutil.rmtree(d, ignore_errors=True)


def cycle(root=None, *, runner=None, http=None, sleep=time.sleep, git=_git, builder=None, poster=None,
          config=None) -> str:
    """One pass; returns the sha's state (idle | deployed | rolled-back | failed | failed-network | skipped)."""
    root = Path(root or REPO)
    runner = runner or dp._default_runner
    http = http or dp._default_http
    builder = builder or _default_builder
    poster = poster or _default_poster
    state = load_state(root)
    state["last_cycle_at"] = dp.now_iso()
    try:
        sha = retry(lambda: fetch_main(root, git), what="fetch", sleep=sleep)
    except Exception as e:  # noqa: BLE001
        state["last_error"] = describe(e)[-400:] if not tls_reason(e) else describe(e)
        save_state(state, root)
        dp.log(f"owner: fetch failed — {describe(e)}")
        return "failed-network" if is_network_error(e) else "failed"
    entry = (state.get("shas") or {}).get(sha) or {}
    if entry.get("state") in TERMINAL or entry.get("cycles", 0) >= MAX_CYCLES:
        save_state(state, root)
        return "idle"
    cycles = entry.get("cycles", 0) + 1
    _record(state, sha, root, state="building", cycles=cycles)
    status = dp.status_file()
    try:
        out = build_root(root) / sha
        if not (out / "manifest.json").is_file():
            dp.log(f"owner: build {sha[:9]} → {out}")
            builder(sha, build_root(root))
        else:
            dp.log(f"owner: build {sha[:9]} reused")
        _prune_builds(root, sha)
        manifest = dp.read_manifest(out)
        version = manifest.get("kb_version", "")
        message = f"{DEPLOY_MESSAGE_PREFIX} {manifest.get('content_sha', sha)} {version} {manifest.get('profile', 'private')}"
        cfg = config or dp.load_config()
        with dp.deploy_lock():
            status.write("deploying", sha, version, dp.now_iso(), url=dp.worker_url(WORKER_MAIN))
            if (dp.parse_message(dp.live_message(WORKER_MAIN, runner)) or {}).get("sha") == sha:
                supersede(state, sha)
                _record(state, sha, root, state="deployed", note="already live")
                status.write("skipped-same", sha, version, dp.now_iso(), url=dp.worker_url(WORKER_MAIN))
                state["last_success_at"] = dp.now_iso()
                save_state(state, root)
                return "skipped"
            previous = entry.get("previous") or \
                retry(lambda: live_version_id(runner), what="deployments list", sleep=sleep)  # first attempt's wins
            _record(state, sha, root, state="uploading", previous=previous)
            with tempfile.TemporaryDirectory(prefix="kb-owner-") as tmp:
                wdir = dp.render_worker_dir(out, WORKER_MAIN, True, cfg, Path(tmp) / WORKER_MAIN)
                vid = retry(lambda: dp.upload_version(wdir, message, tag=sha[:12], runner=_raising(runner)),
                            what="versions upload", sleep=sleep)
            _record(state, sha, root, state="deploying", version_id=vid)
            retry(lambda: dp.deploy_version(WORKER_MAIN, vid, 100, message=message, runner=_raising(runner)),
                  what="versions deploy", sleep=sleep)
            sleep(SETTLE_SECONDS)  # let the new version propagate before judging it
            try:
                bad = health(vid, sha, runner=runner, http=http)
            except Exception as e:  # noqa: BLE001 - an unreadable health is unhealthy
                bad = f"health check raised {type(e).__name__}: {e}"
            if bad:
                return _roll_back(state, sha, root, vid, previous, bad, version, runner, http, sleep, poster, git)
        supersede(state, sha)
        _record(state, sha, root, state="deployed", version_id=vid, error=None)
        state["last_success_at"] = dp.now_iso()
        save_state(state, root)
        status.write("deployed", sha, version, dp.now_iso(), url=dp.worker_url(WORKER_MAIN))
        dp.log(f"owner: deployed {sha[:9]} as {vid}")
        pr = pr_of(sha, root, git)
        if pr:
            poster(pr, "deployed", sha, root, version=vid)
        return "deployed"
    except Exception as e:  # noqa: BLE001
        net = is_network_error(e)
        mod = is_module_error(e) and not entry.get("module_retried")
        st = "failed-module" if mod else "failed-network" if net and cycles < MAX_CYCLES else "failed"
        if mod:  # retried once, after the code check restarts a stale process
            state["shas"][sha]["module_retried"] = True
        tls = tls_reason(e)
        err = f"{type(e).__name__}: {e}"[-400:]
        _record(state, sha, root, state=st, error=f"{tls}; {err}" if tls else err)
        status.write("failed", sha, "", dp.now_iso(), error=f"owner: {describe(e)}"[-500:] if not tls_reason(e) else f"owner: {describe(e)}", url=dp.worker_url(WORKER_MAIN))
        dp.log(f"owner: {sha[:9]} {st} — {describe(e)}")
        return st


def _raising(runner):
    """Turn a network-looking wrangler failure into NetworkError so `retry` sees it."""
    def run(cmd, cwd=None, **kw):
        proc = runner(cmd, cwd=cwd, **kw)
        if proc.returncode != 0 and is_network_error((proc.stderr or "") + (proc.stdout or "")):
            raise NetworkError(((proc.stderr or "") + (proc.stdout or "")).strip()[-400:])
        return proc
    return run


def _roll_back(state, sha, root, vid, previous, reason, version, runner, http, sleep, poster, git):
    dp.log(f"owner: {sha[:9]} unhealthy — {reason}; rolling back to {previous}")
    status = dp.status_file()
    if not previous:
        _record(state, sha, root, state="failed", version_id=vid, error=f"unhealthy, no previous version: {reason}")
        status.write("failed", sha, version, dp.now_iso(), error=f"owner: unhealthy, nothing to roll back to: {reason}")
        return "failed"
    try:
        retry(lambda: dp.deploy_version(WORKER_MAIN, previous, 100, message=f"{DEPLOY_MESSAGE_PREFIX} rollback",
                                        runner=_raising(runner)), what="rollback", sleep=sleep)
        gate = dp.check_gate(WORKER_MAIN, http)
    except Exception as e:  # noqa: BLE001
        err = f"unhealthy: {reason}; ROLLBACK FAILED: {e}"
        _record(state, sha, root, state="rollback-failed", version_id=vid, error=err)
        status.write("failed", sha, version, dp.now_iso(), error=f"owner: {err}"[-500:])
        dp.log(f"owner: {sha[:9]} {err}")
        return "rollback-failed"
    err = f"unhealthy: {reason}" + (f"; AFTER ROLLBACK: {gate}" if gate else "")
    _record(state, sha, root, state="rolled-back", version_id=vid, rolled_back_to=previous, error=err)
    state["rollbacks"] = state.get("rollbacks", 0) + 1
    save_state(state, root)
    status.write("failed", sha, version, dp.now_iso(), error=f"owner rolled back: {err}"[-500:])
    pr = pr_of(sha, root, git)
    if pr:
        poster(pr, "rolled-back", sha, root, version=previous)
    return "rolled-back"


def run(root=None, *, poll=POLL_SECONDS, tick=TICK_SECONDS, max_cycles=None, hasher=code_hash, **seams) -> int:
    """The loop: a cycle on start, then on each wake touch or every `poll` seconds.

    Before each cycle it re-hashes its own code; when that changed (a merge touched kb_distillery/publish or the
    worker modules) it exits 0 so launchd (KeepAlive) restarts it on fresh code before building.
    """
    root = Path(root or REPO)
    started = hasher()
    try:
        with single_instance(root):
            dp.log(f"owner: started (pid {os.getpid()})")
            last_wake, last_run, n = None, 0.0, 0
            while max_cycles is None or n < max_cycles:
                try:
                    mtime = wake_path(root).stat().st_mtime
                except OSError:
                    mtime = None
                now = time.monotonic()
                if n == 0 or mtime != last_wake or now - last_run >= poll:
                    last_wake, last_run = mtime, now
                    if hasher() != started:
                        dp.log("owner: code changed on disk — exiting so launchd restarts it fresh")
                        return 0
                    cycle(root, **seams)
                    n += 1
                    continue
                time.sleep(tick)
    except dp.LockHeld as e:
        print(f"owner: {e}")
        return 1
    return 0


def once(root=None, **seams) -> int:
    try:
        with single_instance(root):
            st = cycle(root, **seams)
    except dp.LockHeld as e:
        print(f"owner: {e} — nudging it instead")
        nudge("once", root)
        return 0
    print(f"owner: {st}")
    return 0 if st in ("idle", "deployed", "skipped") else 1


def fresh(hours: float = 24, root=None, runner=None) -> bool:
    """A successful deploy in the last `hours`: the owner's state, else the newest kb-share deployment."""
    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=hours)

    def recent(iso):
        try:
            t = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            return (t if t.tzinfo else t.astimezone()) >= cutoff
        except ValueError:
            return False

    last = load_state(root).get("last_success_at")
    if last:
        return recent(last)
    runner = runner or dp._default_runner
    proc = runner(dp.wrangler_cmd("deployments", "list", "--name", WORKER_MAIN, "--json"), cwd=str(REPO))
    rows = dp.parse_deployments(proc.stdout) if proc.returncode == 0 else []
    return any(recent(r["created_on"]) and dp.parse_message(r["message"]) for r in rows)


def cmd_status(root=None) -> int:
    state = load_state(root)
    if not state:
        print(f"owner: no state yet ({state_path(root)})")
        return 0
    print(f"last cycle {state.get('last_cycle_at')} · last success {state.get('last_success_at')} · "
          f"rollbacks {state.get('rollbacks', 0)}")
    shas = state.get("shas") or {}
    for sha in sorted(shas, key=lambda s: shas[s].get("at", ""), reverse=True)[:10]:
        e = shas[sha]
        print(f"  {sha[:9]}  {e.get('state', '?'):<14} {e.get('at', '')}  {e.get('version_id') or ''}"
              + (f"  — {e['error'][:120]}" if e.get("error") else ""))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kb_distillery.publish.cloudflare.owner", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="long-lived loop (launchd)")
    sub.add_parser("once", help="one cycle now")
    sub.add_parser("status", help="per-sha state")
    sub.add_parser("nudge", help="touch the wake file")
    f = sub.add_parser("fresh", help="exit 0 when a deploy succeeded in the last --hours")
    f.add_argument("--hours", type=float, default=24)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        return run()
    if args.cmd == "once":
        return once()
    if args.cmd == "nudge":
        print(nudge("cli"))
        return 0
    if args.cmd == "fresh":
        ok = fresh(args.hours)
        print("fresh" if ok else "stale")
        return 0 if ok else 1
    return cmd_status()


if __name__ == "__main__":
    sys.exit(main())
