"""The one door to an LLM. Every feature that calls Claude goes through here, never its own `claude -p`,
SDK or HTTP call, so billing is a flag instead of a rewrite.

Three backends, same Request in, same Result out, results always in input order:
  * subscription — `claude -p` from an empty dir with no tools and the API-key variables removed, so it
    runs on the `claude login` account (usd is what the CLI reports; the subscription is not charged per call);
  * api          — POST /v1/messages with the key from ANTHROPIC_API_KEY or ~/.config/kb-distillery/anthropic_key;
  * batch        — the Message Batches API: half price, results within hours. `run()` submits and waits;
    `submit()` + `collect()` split that across processes (the manifest under .cache/llm/batches/ keeps the order).

Backend precedence: the `backend=` argument, then $KB_LLM_BACKEND, then DEFAULT_BACKEND.
Stdlib only, like kb_distillery.services.chat.
"""
import concurrent.futures as cf
import dataclasses
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from kb_distillery.config import userdir

BACKENDS = ("subscription", "api", "batch")
DEFAULT_BACKEND = "subscription"
ENV_BACKEND = "KB_LLM_BACKEND"

MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5",
          "fable": "claude-fable-5-1"}
# USD per million tokens, Anthropic first-party list prices (checked 2026-10-30, same table as kb_distillery.services.chat).
PRICES = {
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "cache_read": 0.01},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read": 0.20},
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_read": 0.20},
    "claude-fable-5-1": {"in": 10.00, "out": 50.00, "cache_read": 0.25},
}
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif",
               ".webp": "image/webp"}
CACHE_WRITE_5M = 1.25
BATCH_DISCOUNT = 0.5

API_ROOT = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"
KEY_FILE = userdir.path("anthropic_key")
BATCH_MAX = 100_000                     # requests per batch (API limit)
CUSTOM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RETRYABLE = {408, 409, 429, 500, 502, 503, 504, 529}
_SCRUBBED = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")


class LLMError(Exception):
    """A call that cannot be made at all (bad backend, model, ids); per-request failures land in Result.error."""


@dataclasses.dataclass
class Request:
    prompt: str
    id: str = ""                  # custom_id; "r<index>" when empty
    system: str = ""
    model: str = "haiku"          # alias (haiku / sonnet / opus / fable) or a full model id
    max_tokens: int = 8192        # a ceiling, not a cost: thinking counts against it, billing is per token used
    effort: str = "low"
    images: tuple = ()            # image file paths shown before the prompt


@dataclasses.dataclass
class Result:
    id: str
    text: str = ""
    error: str = ""               # empty on success
    usd: float = 0.0
    backend: str = ""
    model: str = ""
    stop_reason: str = ""
    usage: dict = dataclasses.field(default_factory=dict)

    @property
    def ok(self):
        return not self.error


# --- resolution ----------------------------------------------------------------------------------------
def resolve_backend(backend=None):
    b = (backend or os.environ.get(ENV_BACKEND) or DEFAULT_BACKEND).strip().lower()
    if b not in BACKENDS:
        raise LLMError(f"unknown backend {b!r}; pick one of {', '.join(BACKENDS)}")
    return b


def model_id(model):
    m = MODELS.get(model, model)
    if m not in PRICES:
        raise LLMError(f"unknown model {model!r}; pick one of {', '.join(MODELS)} or {', '.join(PRICES)}")
    return m


def cost(model, usage, batch=False):
    """USD for one response's `usage` block."""
    p = PRICES[model_id(model)]
    usd = (usage.get("input_tokens", 0) * p["in"]
           + usage.get("cache_creation_input_tokens", 0) * p["in"] * CACHE_WRITE_5M
           + usage.get("cache_read_input_tokens", 0) * p["cache_read"]
           + usage.get("output_tokens", 0) * p["out"]) / 1e6
    return usd * BATCH_DISCOUNT if batch else usd


def json_object(text):
    """The first {...} span of a reply as a dict (models wrap JSON in prose or fences); None when absent or invalid."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def normalize(requests):
    """Coerce strings to Requests, fill ids, check ids and models up front so a bad batch never leaves the machine."""
    out, seen = [], set()
    for i, r in enumerate(requests):
        r = Request(prompt=r) if isinstance(r, str) else dataclasses.replace(r)
        r.id = r.id or f"r{i}"
        if not CUSTOM_ID_RE.match(r.id):
            raise LLMError(f"request id {r.id!r} must match {CUSTOM_ID_RE.pattern}")
        if r.id in seen:
            raise LLMError(f"duplicate request id {r.id!r}")
        seen.add(r.id)
        model_id(r.model)
        r.images = tuple(r.images)
        for p in r.images:
            if os.path.splitext(p)[1].lower() not in IMAGE_TYPES:
                raise LLMError(f"{p}: images must be one of {', '.join(sorted(IMAGE_TYPES))}")
            if not os.path.isfile(p):
                raise LLMError(f"{p}: no such image")
        out.append(r)
    return out


# --- entry points --------------------------------------------------------------------------------------
def ask(prompt, backend=None, **kw):
    """One prompt → one Result. `kw` are Request fields (system, model, max_tokens, effort)."""
    return run([Request(prompt=prompt, **kw)], backend=backend)[0]


def run(requests, backend=None, workers=4, poll_every=30, wait_s=24 * 3600):
    """Many prompts → Results in the same order. Batch submits, polls every `poll_every` s, gives up after `wait_s`."""
    reqs = normalize(requests)
    b = resolve_backend(backend)
    if not reqs:
        return []
    if b == "batch":
        bid = submit(reqs)
        return collect(bid, poll_every=poll_every, wait_s=wait_s)
    one = _ask_cli if b == "subscription" else _ask_api
    with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(reqs)))) as ex:
        return list(ex.map(one, reqs))


# --- availability: which backends could run, without calling any ---------------------------------------
def _probe(cmd, timeout=8):
    """Run a read-only CLI query → (returncode, stdout). One place to fake in tests; never starts a session."""
    cp = subprocess.run(cmd, env={**_env(), "ANTHROPIC_API_KEY": ""}, stdin=subprocess.DEVNULL,
                        capture_output=True, text=True, timeout=timeout)
    return cp.returncode, cp.stdout


def _which(name):
    return shutil.which(name)


def api_key_source():
    """Where `api_key()` would find a key ("env ANTHROPIC_API_KEY", the key file path) or None. Never the key."""
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "env ANTHROPIC_API_KEY"
    return KEY_FILE if api_key() else None


def _subscription():
    fix = "install Claude Code, then run `claude login` (a Claude subscription)"
    if not _which("claude"):
        return {"ok": False, "why": "the claude CLI is not on PATH", "fix": fix}
    try:
        _, out = _probe(["claude", "auth", "status"])
        start = out.find("{")
        data = json.loads(out[start:]) if start >= 0 else {}      # the CLI may print an escape before the JSON
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"ok": False, "why": "could not read the claude login status", "fix": "run `claude login` in a terminal"}
    if isinstance(data, dict) and data.get("loggedIn") and data.get("authMethod") == "claude.ai":
        return {"ok": True, "why": "logged in to a Claude subscription", "fix": ""}
    return {"ok": False, "why": "the claude CLI is not logged in with a subscription", "fix": "run `claude login`"}


def _keyed(backend):
    src = api_key_source()
    if src:
        return {"ok": True, "why": f"API key found ({src})", "fix": ""}
    return {"ok": False, "why": "no API key",
            "fix": f"set ANTHROPIC_API_KEY or put the key in {KEY_FILE} (the {backend} backend bills the API)"}


def availability():
    """{backend: {ok, why, fix}} for subscription, api and batch, without any LLM call, network or session.
    Subscription = the `claude` CLI is on PATH and `claude auth status` says logged in; api and batch = a key is
    findable by `api_key()`. The app greys AI features out when no backend is ok."""
    return {"subscription": _subscription(), "api": _keyed("api"), "batch": _keyed("batch")}


# --- subscription: claude -p ---------------------------------------------------------------------------
def _env():
    return {k: v for k, v in os.environ.items() if k not in _SCRUBBED and not k.startswith(("PIXI_", "CONDA_"))}


def _cli(cmd, cwd, env, timeout):
    return subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout)


def _ask_cli(r, timeout=600, retries=2):
    """No tools and an empty dir; with images, only Read, run from the first image's folder (the CLI takes no
    image argument, so the model opens the files itself)."""
    res = Result(id=r.id, backend="subscription", model=model_id(r.model))
    prompt = f"{r.system}\n\n{r.prompt}" if r.system else r.prompt
    tools = ["--tools", ""]
    if r.images:
        paths = [os.path.abspath(p) for p in r.images]
        prompt = f"Read the image file{'s' if len(paths) > 1 else ''} {', '.join(paths)} first.\n\n{prompt}"
        tools = ["--tools", "Read", "--allowedTools", "Read"]
    for attempt in range(retries + 1):
        with tempfile.TemporaryDirectory(prefix="kb-llm-") as tmp:
            cwd = os.path.dirname(os.path.abspath(r.images[0])) if r.images else tmp
            cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", res.model, "--effort", r.effort,
                   *tools, "--strict-mcp-config", "--no-session-persistence"]
            try:
                cp = _cli(cmd, cwd, _env(), timeout)
                out = json.loads(cp.stdout) if cp.stdout.strip() else None
            except (OSError, subprocess.TimeoutExpired, ValueError) as e:
                cp, out, res.error = None, None, str(e)[:200]
        if cp is not None:
            if not isinstance(out, dict):
                res.error = f"claude exited {cp.returncode}: {(cp.stderr or cp.stdout or '')[:200]}"
            else:
                res.usd = out.get("total_cost_usd") or 0.0
                res.usage = out.get("usage") or {}
                if out.get("is_error") or cp.returncode != 0:
                    res.error = f"claude exited {cp.returncode}: {str(out.get('result'))[:200]}"
                elif not out.get("result"):
                    res.error = "empty result"
                else:
                    res.text, res.error, res.stop_reason = out["result"], "", out.get("stop_reason") or ""
                    return res
        if attempt < retries:
            _sleep(5 * (attempt + 1))
    return res


# --- api: /v1/messages ---------------------------------------------------------------------------------
def api_key():
    k = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if k:
        return k
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _ssl():
    from kb_distillery.ingest.net import ssl_context   # OS trust store / keychain roots (TLS-inspecting proxies); no vault needed
    return ssl_context()


class HTTPFail(Exception):
    def __init__(self, status, message):
        super().__init__(f"API {status}: {message}" if status else message)
        self.status = status


def _http(method, url, key, body=None, timeout=600):
    """→ response bytes; raises HTTPFail (status 0 when the API was unreachable)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        raise HTTPFail(e.code, detail or str(e.reason)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise HTTPFail(0, f"cannot reach the API: {getattr(e, 'reason', e)}") from None


def _call(method, path, body=None, retries=3):
    key = api_key()
    if not key:
        raise HTTPFail(0, f"no API key: set ANTHROPIC_API_KEY or write {KEY_FILE}")
    for attempt in range(retries + 1):
        try:
            raw = _http(method, path if path.startswith("http") else API_ROOT + path, key, body)
            return raw
        except HTTPFail as e:
            if attempt == retries or (e.status and e.status not in RETRYABLE):
                raise
            _sleep(2 ** attempt * 2)


def _image_block(path):
    import base64
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": IMAGE_TYPES[os.path.splitext(path)[1].lower()],
                                        "data": data}}


def params(r):
    content = ([*map(_image_block, r.images), {"type": "text", "text": r.prompt}] if r.images else r.prompt)
    p = {"model": model_id(r.model), "max_tokens": r.max_tokens,
         "messages": [{"role": "user", "content": content}],
         "output_config": {"effort": r.effort}}
    if r.system:
        p["system"] = r.system
    return p


def _from_message(res, msg, batch=False):
    res.usage = msg.get("usage") or {}
    res.stop_reason = msg.get("stop_reason") or ""
    res.usd = cost(res.model, res.usage, batch=batch)
    res.text = "".join(b.get("text", "") for b in msg.get("content") or [] if b.get("type") == "text")
    if res.stop_reason == "refusal":
        res.error = "refused: " + str((msg.get("stop_details") or {}).get("category") or "")
    elif res.stop_reason == "max_tokens":
        res.error = "cut at max_tokens (text kept)"
    elif not res.text:
        res.error = "empty result"
    return res


def _ask_api(r):
    res = Result(id=r.id, backend="api", model=model_id(r.model))
    try:
        msg = json.loads(_call("POST", "/messages", params(r)))
    except (HTTPFail, ValueError) as e:
        res.error = str(e)[:300]
        return res
    return _from_message(res, msg)


# --- batch: /v1/messages/batches -----------------------------------------------------------------------
def batch_dir():
    from kb_distillery import paths
    return os.path.join(paths.CACHE_PATH, "llm", "batches")


def _manifest(bid, reqs=None, root=None):
    path = os.path.join(root or batch_dir(), f"{bid}.json")
    if reqs is None:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    m = {"id": bid, "submitted": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "requests": [{"id": r.id, "model": model_id(r.model)} for r in reqs]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1)
    return m


def submit(requests, root=None):
    """Send one batch → its id. The manifest keeps the request order so `collect` can run in another process."""
    reqs = normalize(requests)
    if not reqs:
        raise LLMError("empty batch")
    if len(reqs) > BATCH_MAX:
        raise LLMError(f"{len(reqs)} requests; a batch holds at most {BATCH_MAX}")
    out = json.loads(_call("POST", "/messages/batches",
                           {"requests": [{"custom_id": r.id, "params": params(r)} for r in reqs]}))
    _manifest(out["id"], reqs, root=root)
    return out["id"]


def status(bid):
    """The batch object: processing_status (in_progress / canceling / ended), request_counts, results_url."""
    return json.loads(_call("GET", f"/messages/batches/{bid}"))


def collect(bid, poll_every=30, wait_s=24 * 3600, root=None):
    """Wait for the batch to end, then → Results in submit order. Requests the API never answered get an error."""
    m = _manifest(bid, root=root)
    deadline = time.monotonic() + wait_s
    while True:
        st = status(bid)
        if st.get("processing_status") == "ended":
            break
        if time.monotonic() + poll_every > deadline:
            return [Result(id=q["id"], backend="batch", model=q["model"],
                           error=f"batch {bid} still {st.get('processing_status')} after {wait_s}s; "
                                 f"collect it later") for q in m["requests"]]
        _sleep(poll_every)
    lines = _call("GET", st.get("results_url") or f"/messages/batches/{bid}/results").decode("utf-8")
    got = {}
    for line in lines.splitlines():
        if line.strip():
            row = json.loads(line)
            got[row.get("custom_id")] = row.get("result") or {}
    out = []
    for q in m["requests"]:
        res = Result(id=q["id"], backend="batch", model=q["model"])
        r = got.get(q["id"])
        if r is None:
            res.error = "missing from batch results"
        elif r.get("type") == "succeeded":
            _from_message(res, r.get("message") or {}, batch=True)
        elif r.get("type") == "errored":
            res.error = "errored: " + str((r.get("error") or {}).get("error", {}).get("message")
                                          or r.get("error"))[:300]
        else:
            res.error = str(r.get("type") or "unknown result")
        out.append(res)
    return out


def _sleep(s):
    time.sleep(s)
