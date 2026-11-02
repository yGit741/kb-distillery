"""Thin Cloudflare helpers for the share CLI (snapshots; mirrored by the W3 panel Worker).

wrangler (`npx wrangler@<pinned> … --json`) is used where it has a command — deployments,
versions, delete — and the REST / GraphQL API (urllib) where it does not: the list of Worker
scripts and the 7-day request counts (`workersInvocationsAdaptive`).

Auth for REST/GraphQL: `CLOUDFLARE_API_TOKEN` when set, else wrangler's own OAuth token from
`~/Library/Preferences/.wrangler/config/default.toml` (refreshed through `wrangler whoami` when
expired). The token is never printed.

Every network call goes through three seams so tests can mock them without touching the
network: `run` (subprocess), `http_json` (REST/GraphQL) and `http_get` (plain GET, e.g. a
snapshot's `manifest.json`).
"""
import datetime as _dt
import json
import os
import socket
import ssl
import subprocess
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from kb_distillery.publish.cloudflare.contracts import REPO, WRANGLER_VERSION

ACCOUNT_ID = os.environ.get("KB_CLOUDFLARE_ACCOUNT_ID") or "7803af2d776eeea4c226f8e594121a10"
API_BASE = "https://api.cloudflare.com/client/v4"
GRAPHQL_URL = f"{API_BASE}/graphql"
WRANGLER_CONFIG = Path.home() / "Library" / "Preferences" / ".wrangler" / "config" / "default.toml"
REST_TIMEOUT = 30
VIEWS_DAYS = 7


class CloudflareError(RuntimeError):
    """A Cloudflare call that failed in a way the caller must report (auth, API error)."""


# ---------- seams ----------

def wrangler_cmd(*args: str) -> list:
    return ["npx", f"wrangler@{WRANGLER_VERSION}", *args]


def run(cmd, cwd=None, timeout=600) -> subprocess.CompletedProcess:
    """Seam: run a subprocess (wrangler)."""
    return subprocess.run(cmd, cwd=str(cwd or REPO), capture_output=True, text=True, timeout=timeout)


EXTRA_CA_ENV = ("KB_SHARE_CA_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS")


def ssl_context() -> Optional[ssl.SSLContext]:
    """TLS context for a Mac behind a corporate TLS proxy.

    `truststore` (system keychain) when importable; else the default context plus the CA bundle
    named by the first set of KB_SHARE_CA_FILE / REQUESTS_CA_BUNDLE / NODE_EXTRA_CA_CERTS (the
    same file wrangler/node already trusts). Proxy CAs often lack an Authority Key Identifier,
    which Python ≥ 3.13 rejects under VERIFY_X509_STRICT, so that flag is cleared only when an
    extra bundle is loaded. None → urllib's default behaviour.
    """
    try:
        import truststore  # noqa: WPS433
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        pass
    for var in EXTRA_CA_ENV:
        cafile = os.environ.get(var, "").strip()
        if cafile and os.path.isfile(cafile):
            ctx = ssl.create_default_context()
            try:
                ctx.load_verify_locations(cafile=cafile)
            except (ssl.SSLError, OSError):
                continue
            ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
            return ctx
    return None


def http_json(method: str, url: str, body: Optional[dict] = None, headers: Optional[dict] = None,
              timeout: int = REST_TIMEOUT) -> tuple:
    """Seam: (status, parsed JSON or None) of a REST/GraphQL call. Network errors → (0, None)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Accept": "application/json", "User-Agent": "kb-share"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as res:
            return res.status, _loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, _loads(e.read())
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, None


def http_get(url: str, timeout: int = 10) -> tuple:
    """Seam: (status, bytes) of a plain GET; (0, b'') when unreachable; raises TimeoutError on timeout."""
    req = urllib.request.Request(url, headers={"User-Agent": "kb-share"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (socket.timeout, TimeoutError):
        raise TimeoutError(url)
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise TimeoutError(url)
        return 0, b""
    except OSError:
        return 0, b""


def _loads(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


# ---------- auth ----------

def _read_wrangler_config() -> dict:
    try:
        return tomllib.loads(WRANGLER_CONFIG.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _expired(cfg: dict) -> bool:
    exp = cfg.get("expiration_time")
    if not exp:
        return False
    try:
        when = _dt.datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    return when <= _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=1)


def api_token() -> str:
    """CLOUDFLARE_API_TOKEN, else wrangler's OAuth token (refreshed via `wrangler whoami` when stale)."""
    env = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if env:
        return env
    cfg = _read_wrangler_config()
    if cfg.get("oauth_token") and _expired(cfg):
        try:
            run(wrangler_cmd("whoami"), timeout=120)  # wrangler refreshes the token on use
        except (OSError, subprocess.SubprocessError):
            pass
        cfg = _read_wrangler_config()
    token = str(cfg.get("oauth_token") or "").strip()
    if not token:
        raise CloudflareError("no Cloudflare credentials: set CLOUDFLARE_API_TOKEN or run "
                              f"`npx wrangler@{WRANGLER_VERSION} login`")
    return token


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {api_token()}"}


def _rest(method: str, path: str, body: Optional[dict] = None) -> dict:
    status, payload = http_json(method, f"{API_BASE}{path}", body, _auth_headers())
    if status == 0 or not isinstance(payload, dict):
        raise CloudflareError(f"Cloudflare API {method} {path}: unreachable or non-JSON reply (status {status})")
    if status >= 400 or not payload.get("success", True):
        errs = "; ".join(f"{e.get('code')}: {e.get('message')}" for e in payload.get("errors") or []) or f"HTTP {status}"
        raise CloudflareError(f"Cloudflare API {method} {path} failed: {errs}")
    return payload


# ---------- Workers ----------

def list_scripts() -> list:
    """[{name, created_on, modified_on}] of every Worker script in the account."""
    payload = _rest("GET", f"/accounts/{ACCOUNT_ID}/workers/scripts")
    out = []
    for s in payload.get("result") or []:
        out.append({"name": s.get("id"), "created_on": s.get("created_on"), "modified_on": s.get("modified_on")})
    return sorted(out, key=lambda s: s["name"] or "")


def _json_out(proc: subprocess.CompletedProcess):
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError):
        return None


def latest_deployment(name: str) -> Optional[dict]:
    """{message, created_on, version_id} of the deployment currently serving `name`, or None."""
    deployments = _json_out(run(wrangler_cmd("deployments", "list", "--name", name, "--json")))
    if not deployments:
        return None
    try:
        dep = deployments[-1]
        versions = dep.get("versions") or []
        live = max(versions, key=lambda v: v.get("percentage", 0))["version_id"] if versions else None
        message = (dep.get("annotations") or {}).get("workers/message")
        if message is None and live:
            for v in _json_out(run(wrangler_cmd("versions", "list", "--name", name, "--json"))) or []:
                if v.get("id") == live:
                    message = (v.get("annotations") or {}).get("workers/message")
                    break
        return {"message": message, "created_on": dep.get("created_on"), "version_id": live}
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def list_versions(name: str) -> list:
    """Every uploaded version of `name`, newest first: [{version_id, created_on, message}] — the
    audit trail of a snapshot that was updated in place. [] when wrangler cannot list them."""
    out = []
    for v in _json_out(run(wrangler_cmd("versions", "list", "--name", name, "--json"))) or []:
        if not isinstance(v, dict) or not v.get("id"):
            continue
        meta = v.get("metadata") or {}
        out.append({"version_id": v["id"], "created_on": meta.get("created_on") or v.get("created_on"),
                    "message": (v.get("annotations") or {}).get("workers/message")})
    return sorted(out, key=lambda v: v.get("created_on") or "", reverse=True)


def delete_worker(name: str) -> Optional[str]:
    """`wrangler delete --name <name> --force`; None on success, else the error tail."""
    proc = run(wrangler_cmd("delete", "--name", name, "--force"), timeout=300)
    if proc.returncode == 0:
        return None
    return ((proc.stderr or "") + (proc.stdout or "")).strip()[-600:] or f"exit {proc.returncode}"


# ---------- analytics ----------

_VIEWS_QUERY = """
query ($account: string!, $since: Time!, $until: Time!) {
  viewer {
    accounts(filter: {accountTag: $account}) {
      workersInvocationsAdaptive(limit: 1000, filter: {datetime_geq: $since, datetime_leq: $until}) {
        sum { requests }
        dimensions { scriptName }
      }
    }
  }
}
"""


def views(names, days: int = VIEWS_DAYS) -> Optional[dict]:
    """{worker: requests in the last `days`} or None when analytics is unavailable (not an error)."""
    until = _dt.datetime.now(_dt.timezone.utc)
    since = until - _dt.timedelta(days=days)
    body = {"query": _VIEWS_QUERY,
            "variables": {"account": ACCOUNT_ID, "since": since.isoformat(timespec="seconds").replace("+00:00", "Z"),
                          "until": until.isoformat(timespec="seconds").replace("+00:00", "Z")}}
    try:
        status, payload = http_json("POST", GRAPHQL_URL, body, _auth_headers())
    except CloudflareError:
        return None
    if status != 200 or not isinstance(payload, dict) or payload.get("errors"):
        return None
    try:
        rows = payload["data"]["viewer"]["accounts"][0]["workersInvocationsAdaptive"]
    except (KeyError, IndexError, TypeError):
        return None
    counts = {n: 0 for n in names}
    for row in rows or []:
        script = (row.get("dimensions") or {}).get("scriptName")
        if script in counts:
            counts[script] += int((row.get("sum") or {}).get("requests") or 0)
    return counts


# ---------- snapshot sites ----------

def fetch_manifest(url: str, timeout: int = 10) -> tuple:
    """('ok', manifest) | ('timeout', None) | ('down', None) for `<url>/manifest.json`."""
    try:
        status, raw = http_get(url.rstrip("/") + "/manifest.json", timeout=timeout)
    except TimeoutError:
        return "timeout", None
    if status != 200:
        return "down", None
    data = _loads(raw)
    return ("ok", data) if isinstance(data, dict) else ("down", None)
