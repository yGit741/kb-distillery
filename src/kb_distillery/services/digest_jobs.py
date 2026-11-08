"""Digest jobs from the app: a preview (backend, cost, time) and full digests run in a worker process, one source at a time.

HTTP-free (`kb_distillery.server.routers.digest_jobs` relays `JobError(status, message)`). A job lives in `meta/.jobs/<id>/`
(engine runtime state, never knowledge: gitignored by `distill init`, and added to the local exclude file of an older kb):

  job.json     the job and every source's status (pending -> filling -> digesting -> finalized | failed | skipped | cancelled)
  worker.log   what the worker printed
  claims/      the filled claims.json of each source, before its session takes it

  preview(raws, backend, model)   no model call: tokens from the extracted text, USD from `llm.cost`, a time estimate
  start_job(raws, backend, model) checks, writes job.json, spawns `python -m kb_distillery.services.digest_jobs run <id>`
  cancel(job_id)                  SIGTERM to the worker (a finalize in flight ends first), SIGKILL to its group after a
                                  minute; the open session rolls back
  events(job_id)                  (event, data) pairs for `server.sse`: `job` on every change, `end` when it stops

The worker reuses `ingest.digest_many`: `build_request` makes the claim-fill request, `llm.run` sends it (batch: every
source in one batch; subscription / api: one source at a time), `extract.claims_from_result` validates the reply and
`digest_one` runs the session (extract, map, draft, finalize), so each finished source is its own `kb(digest)` commit.
Sources finalized before a cancel stay committed. One job runs at a time per kb, and never beside an open ops session.

Billing defaults (`default_backend`): an explicit backend wins, then $KB_LLM_BACKEND; a job above `[llm] bulk_threshold`
sources (kb.toml, default 5) goes to the standard API; a smaller one to the subscription when `claude` is logged in, else
the API. Batch is never a default: it is chosen per job, with its hours-long ETA.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import secrets
import signal
import subprocess
import sys
import time

from kb_distillery import llm
from kb_distillery.config import kb as kbconfig
from kb_distillery.config.layout import JOBS_DIR
from kb_distillery.config.paths import vault_root
from kb_distillery.ingest import digest_many, extract
from kb_distillery.ingest import paths as ingest_paths
from kb_distillery.ingest import session as session_mod
from kb_distillery.ingest import verify
from kb_distillery.ops import core
from kb_distillery.vault import views

DEFAULT_ROOT = vault_root()
BULK_THRESHOLD = 5                 # [llm] bulk_threshold: above it a job defaults to the standard API
DEPTH = "full"                     # a job runs full digests
TIER = "standard"                  # placeholder until model tiers (R3.2) fill it
SECONDS = {"subscription": 180, "api": 120, "batch": 120}   # rough wall time per source: fill + map/draft/finalize/lint
BATCH_SECONDS = 4 * 3600           # a typical batch wait (the API allows up to 24 hours)
BATCH_ETA = "a few hours, up to 24 (half price)"
CANCEL_WAIT = 60.0                 # seconds between SIGTERM and SIGKILL (a finalize in flight runs lint, then commits)
POLL = 0.5                         # seconds between job.json reads in `events`
PING_EVERY = 10                    # polls between keep-alive pings on an unchanged job
STOP_AFTER = digest_many.STOP_AFTER
LIVE = ("queued", "running")
START_GRACE = 60.0                 # seconds a queued job may go without its worker's pid
_PROCS: dict[str, subprocess.Popen] = {}      # job id -> worker started by this process (to reap and poll it)


class JobError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


# --- storage ---------------------------------------------------------------------------------------------------
def jobs_dir(root: str) -> str:
    return os.path.join(root, JOBS_DIR)


def job_dir(root: str, job_id: str) -> str:
    if not job_id or not all(c.isalnum() or c == "-" for c in job_id):
        raise JobError(404, f"no job {job_id!r}")
    return os.path.join(jobs_dir(root), job_id)


def _save(root: str, job: dict) -> None:
    d = job_dir(root, job["id"])
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "job.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(job, f, indent=1, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def _load(root: str, job_id: str) -> dict:
    try:
        with open(os.path.join(job_dir(root, job_id), "job.json"), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        raise JobError(404, f"no job {job_id!r}") from None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@contextlib.contextmanager
def _lock(root: str):
    os.makedirs(jobs_dir(root), exist_ok=True)
    with open(os.path.join(jobs_dir(root), ".lock"), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


# --- defaults --------------------------------------------------------------------------------------------------
def bulk_threshold(root: str) -> int:
    try:
        value = kbconfig.load_dir(root, strict=False).section("llm").get("bulk_threshold", BULK_THRESHOLD)
        return int(value)
    except (kbconfig.KbConfigError, TypeError, ValueError):
        return BULK_THRESHOLD


def default_backend(n_sources: int, root: str, backend: str | None = None) -> tuple[str, str]:
    """(backend, why) for a job of `n_sources`; an unknown name raises JobError(422)."""
    try:
        if backend:
            return llm.resolve_backend(backend), "chosen for this run"
        if os.environ.get(llm.ENV_BACKEND, "").strip():
            return llm.resolve_backend(), f"${llm.ENV_BACKEND}"
    except llm.LLMError as e:
        raise JobError(422, str(e)) from None
    limit = bulk_threshold(root)
    if n_sources > limit:
        return "api", f"more than {limit} sources ([llm] bulk_threshold): the standard API"
    if llm.availability()["subscription"]["ok"]:
        return "subscription", "claude is logged in to a subscription"
    return "api", "claude is not logged in to a subscription: the standard API"


def _model(model: str | None) -> str:
    m = model or digest_many.MODEL
    try:
        llm.model_id(m)
    except llm.LLMError as e:
        raise JobError(422, str(e)) from None
    return m


def _check_raws(raws) -> list[str]:
    out = []
    for raw in dict.fromkeys(r.strip() for r in raws or [] if r and r.strip()):
        try:
            out.append(verify.verify_raw(raw))
        except ValueError as e:
            raise JobError(422, str(e)) from None
    if not out:
        raise JobError(422, "no sources: pass one or more raw paths")
    return out


# --- preview ---------------------------------------------------------------------------------------------------
def _estimate(reqs, model: str, backend: str) -> dict:
    tokens_in = round(sum(len(r.prompt) for r in reqs) / 3.5)
    tokens_out = digest_many.OUT_TOKENS * len(reqs)
    batch = backend == "batch"
    usd = llm.cost(model, {"input_tokens": tokens_in, "output_tokens": tokens_out}, batch=batch)
    worst = llm.cost(model, {"input_tokens": tokens_in, "output_tokens": extract.FILL_MAX_TOKENS * len(reqs)}, batch=batch)
    seconds = SECONDS[backend] * len(reqs) + (BATCH_SECONDS if batch and reqs else 0)
    eta = BATCH_ETA if batch else f"about {max(1, round(seconds / 60))} min"
    return {"tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": round(usd, 4), "cost_worst_usd": round(worst, 4),
            "billed_usd": 0.0 if backend == "subscription" else round(usd, 4), "seconds": seconds, "eta": eta}


def preview(raws, backend: str | None = None, model: str | None = None, root: str | None = None) -> dict:
    """What a job over `raws` would cost and take on its default backend and on each of the three. No model call."""
    root = root or DEFAULT_ROOT
    raws = _check_raws(raws)
    model = _model(model)
    chosen, why = default_backend(len(raws), root, backend)
    reqs, skipped = [], []
    for raw in raws:
        req, reason = digest_many.build_request(raw, model)
        (reqs.append(req) if req else skipped.append({"raw": raw, "reason": reason}))
    avail = llm.availability()
    options = [{"backend": b, "available": bool(avail[b]["ok"]), "why": avail[b]["why"], **_estimate(reqs, model, b)}
               for b in llm.BACKENDS]
    return {"tier": TIER, "depth": DEPTH, "provider": llm.DEFAULT_PROVIDER, "model": llm.model_id(model),
            "backend": chosen, "backend_why": why, "sources": len(raws), "requests": len(reqs), "skipped": skipped,
            **_estimate(reqs, model, chosen), "options": options}


# --- jobs ------------------------------------------------------------------------------------------------------
def _alive(job: dict) -> bool:
    proc = _PROCS.get(job["id"])
    if proc is not None:
        return proc.poll() is None
    pid = job.get("pid")
    if not pid:                                           # spawned but not started yet (or never started: give up after a minute)
        return job["status"] == "queued" and time.time() - job.get("created_ts", 0) < START_GRACE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _session_of(raw: str) -> str | None:
    try:
        return session_mod.session_id(ingest_paths.sha1_file(raw), digest_many.scope_for(raw))
    except OSError:
        return None


def _settle(raw: str | None) -> tuple[str | None, str | None]:
    """(state, session id) of the session a stopped worker left for `raw`: an open or half-finalized one is rolled back
    here ("rolled back"), one the worker rolled back itself is "rolled back" too, a closed one is "finalized"."""
    sid = raw and _session_of(raw)
    if not sid:
        return None, None
    try:
        status = ingest_paths.load_session(sid).get("status")
    except (FileNotFoundError, ValueError):
        return None, sid
    if status in ("open", "finalizing"):
        session_mod.rollback(sid, "aborted")
        return "rolled back", sid
    return {"aborted": "rolled back", "closed": "finalized"}.get(status), sid


def _close(root: str, job: dict, status: str, note: str) -> dict:
    """Mark a stopped job `status`: its current source rolls back, every unfinished source takes the note."""
    current = job.get("current")
    state, sid = _settle(current)
    for s in job["sources"]:
        if s["raw"] == current and state == "finalized" and s["status"] == "digesting":
            s.update(status="finalized", page=_page_of(sid),
                     note="finished while the job stopped; if its kb(digest) commit is missing, `ops sync` makes it")
        elif s["status"] in ("pending", "filling", "digesting"):
            s["status"] = "cancelled" if status == "cancelled" else "failed"
            s["note"] = note + (" (its session rolled back)" if state == "rolled back" and s["raw"] == current else "")
    job.update(status=status, current=None, finished=_now(), error=None if status == "cancelled" else note)
    _save(root, job)
    _PROCS.pop(job["id"], None)
    return job


def _reconcile(root: str, job: dict) -> dict:
    if job["status"] not in LIVE:
        proc = _PROCS.pop(job["id"], None)                    # reap a worker that ended on its own
        if proc is not None:
            proc.poll()
        return job
    if not _alive(job):
        job = _load(root, job["id"])                          # the worker may have written its last state as it went
        if job["status"] in LIVE:
            return _close(root, job, "failed", "the worker stopped before the job ended")
    return job


def get(job_id: str, root: str | None = None) -> dict:
    root = root or DEFAULT_ROOT
    return _reconcile(root, _load(root, job_id))


def list_jobs(root: str | None = None) -> list[dict]:
    root = root or DEFAULT_ROOT
    d = jobs_dir(root)
    out = []
    for name in sorted(os.listdir(d), reverse=True) if os.path.isdir(d) else []:
        if os.path.isfile(os.path.join(d, name, "job.json")):
            with contextlib.suppress(JobError):
                out.append(get(name, root))
    return out


def _spawn(root: str, job_id: str) -> subprocess.Popen:
    """The worker: its own process group (so a last-resort SIGKILL reaches its `claude -p` and finalize children), no stdin."""
    log = open(os.path.join(job_dir(root, job_id), "worker.log"), "ab")
    try:
        return subprocess.Popen([sys.executable, "-m", "kb_distillery.services.digest_jobs", "run", job_id],
                                cwd=root, env={**os.environ, "KB_ROOT": root}, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    finally:
        log.close()


spawn = _spawn                     # tests replace this


def start_job(raws, backend: str | None = None, model: str | None = None, root: str | None = None) -> dict:
    root = root or DEFAULT_ROOT
    raws = _check_raws(raws)
    model = _model(model)
    chosen, why = default_backend(len(raws), root, backend)
    avail = llm.availability()[chosen]
    if not avail["ok"]:
        raise JobError(422, f"the {chosen} backend is not available: {avail['why']}" + (f" ({avail['fix']})" if avail["fix"] else ""))
    with _lock(root):
        live = [j for j in list_jobs(root) if j["status"] in LIVE]
        if live:
            raise JobError(409, f"job {live[0]['id']} is still running: wait for it or cancel it")
        session = core.current_session(root)
        if session:
            raise JobError(409, f"an ops session is open ({session['op']} {session['target']}) - finish it first")
        for raw in raws:
            if session_mod.find_open_session(raw):
                raise JobError(409, f"an ingest session is already open for {raw}: finish or abort it first")
        views.ensure_ignored(root, f"{JOBS_DIR}/")
        job_id = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
        job = {"id": job_id, "status": "queued", "created": _now(), "created_ts": time.time(), "started": None, "finished": None,
               "backend": chosen, "backend_why": why, "model": llm.model_id(model), "provider": llm.DEFAULT_PROVIDER,
               "tier": TIER, "depth": DEPTH, "pid": None, "current": None, "spent_usd": 0.0, "error": None,
               "sources": [{"raw": r, "status": "pending", "note": "", "page": None, "seconds": None} for r in raws]}
        _save(root, job)
        try:
            proc = spawn(root, job_id)
        except OSError as e:
            _close(root, job, "failed", f"the worker did not start: {e}")
            raise JobError(500, f"the digest worker did not start: {e}") from None
        _PROCS[job_id] = proc                             # the worker writes its own pid when it starts
    return {**_load(root, job_id), "pid": proc.pid}


def cancel(job_id: str, root: str | None = None) -> dict:
    """Stop a live job: SIGTERM to the worker (it rolls back its open session; a finalize in flight finishes and commits
    first), SIGKILL to its whole process group after CANCEL_WAIT; whatever session is left open rolls back here."""
    root = root or DEFAULT_ROOT
    with _lock(root):
        return _cancel(root, job_id)


def _cancel(root: str, job_id: str) -> dict:
    job = get(job_id, root)
    if job["status"] not in LIVE:
        raise JobError(409, f"job {job_id} already ended ({job['status']})")
    proc = _PROCS.get(job_id)
    pid = proc.pid if proc is not None else job.get("pid")
    if pid:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + CANCEL_WAIT
        while _alive(job) and time.monotonic() < deadline:
            time.sleep(0.1)
        if _alive(job):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pid, signal.SIGKILL)
            proc = _PROCS.get(job_id)
            if proc is not None:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(5)
    job = _load(root, job_id)
    if job["status"] not in LIVE:                             # it ended on its own just before the signal
        _PROCS.pop(job_id, None)
        return job
    return _close(root, job, "cancelled", "cancelled")


def events(job_id: str, root: str | None = None, poll: float = POLL):
    """(event, data) pairs for `server.sse.sse_response`: `job` whenever job.json changes, `end` once it has stopped."""
    root = root or DEFAULT_ROOT
    last, n = None, 0
    while True:
        job = get(job_id, root)
        if job != last:
            yield "job", job
            last = job
        elif n % PING_EVERY == 0:
            yield "ping", None                                # lets the stream notice a client that went away
        if job["status"] not in LIVE:
            yield "end", {"id": job_id, "status": job["status"]}
            return
        n += 1
        time.sleep(poll)


# --- worker ----------------------------------------------------------------------------------------------------
def _fill(root: str, job: dict, raws: list[str], model: str, backend: str) -> dict:
    """Fill claims for `raws` through kb_distillery.llm → {raw: claims path}; a source that cannot be filled is marked failed."""
    by_raw = {s["raw"]: s for s in job["sources"]}
    reqs, templates = [], {}
    for raw in raws:
        req, why = digest_many.build_request(raw, model)
        if req is None:
            by_raw[raw].update(status="skipped", note=why)
            continue
        reqs.append((raw, req))
        templates[raw] = why                               # build_request returns (request, template)
    results = llm.run([r for _, r in reqs], backend=backend) if reqs else []
    out = {}
    os.makedirs(os.path.join(job_dir(root, job["id"]), "claims"), exist_ok=True)
    for (raw, _), r in zip(reqs, results):
        job["spent_usd"] = round(job["spent_usd"] + (r.usd or 0.0), 5)
        if not r.ok and not r.text:
            by_raw[raw].update(status="failed", note=f"fill failed: {r.error}"[:300])
            continue
        claims, reason = extract.claims_from_result(r, templates[raw])
        if reason:
            by_raw[raw].update(status="failed", note=f"fill rejected: {reason}"[:300])
            continue
        path = os.path.join(job_dir(root, job["id"]), "claims", f"{digest_many.request_id(raw)}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(claims, f, indent=2, ensure_ascii=False)
        out[raw] = path
    return out


def _page_of(sha: str) -> str | None:
    try:
        with open(os.path.join(ingest_paths.session_dir(sha), "plan.json"), encoding="utf-8") as f:
            slug = json.load(f).get("wiki_slug")
        return f"wiki/{slug}.md" if slug else None
    except (OSError, ValueError):
        return None


def _on_term(signum, frame):
    raise SystemExit(128 + signum)


def run_job(job_id: str, root: str | None = None) -> int:
    """The worker body: fill, then one `digest_one` session per source, saving job.json after every step."""
    root = root or DEFAULT_ROOT
    with _lock(root):
        job = _load(root, job_id)
        if job["status"] != "queued":                           # cancelled or given up on before it started
            return 0
        job.update(status="running", started=_now(), pid=os.getpid())   # its process group id too (start_new_session)
        _save(root, job)
    backend, model = job["backend"], job["model"]
    pending = [s for s in job["sources"] if s["status"] == "pending"]
    failed_row = 0
    try:
        claims = {}
        if backend == "batch":                                  # one batch for every source, then the sessions
            for s in pending:
                s["status"] = "filling"
            job["current"] = None
            _save(root, job)
            claims = _fill(root, job, [s["raw"] for s in pending], model, backend)
            _save(root, job)
        for s in pending:
            if s["status"] in ("failed", "skipped"):
                continue
            if failed_row >= STOP_AFTER:
                s.update(status="skipped", note=f"stopped: {STOP_AFTER} failed sources in a row")
                continue
            t0 = time.monotonic()
            job["current"] = s["raw"]
            if backend != "batch":
                s["status"] = "filling"
                _save(root, job)
                claims.update(_fill(root, job, [s["raw"]], model, backend))
                if s["raw"] not in claims:
                    failed_row += s["status"] == "failed"
                    s["seconds"] = round(time.monotonic() - t0, 1)
                    _save(root, job)
                    continue
            s["status"] = "digesting"
            _save(root, job)
            try:
                sha = digest_many.digest_one(s["raw"], claims[s["raw"]])
                s.update(status="finalized", page=_page_of(sha), note="")
                failed_row = 0
            except Exception as e:                              # the session rolled itself back
                s.update(status="failed", note=str(e)[:300])
                failed_row += 1
            s["seconds"] = round(time.monotonic() - t0, 1)
            job["current"] = None
            _save(root, job)
        ok = any(s["status"] == "finalized" for s in job["sources"]) or not pending
        job.update(status="done" if ok else "failed", current=None, finished=_now(),
                   error=None if ok else "no source was digested")
        _save(root, job)
        return 0 if ok else 1
    except SystemExit:                                          # cancel: the parent finishes the bookkeeping
        _save(root, job)
        raise
    except Exception as e:                                      # noqa: BLE001 - recorded on the job, never lost
        _close(root, job, "failed", f"worker error: {e}"[:300])
        return 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] != "run":
        print("usage: python -m kb_distillery.services.digest_jobs run <job-id>", file=sys.stderr)
        return 2
    signal.signal(signal.SIGTERM, _on_term)
    return run_job(argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
