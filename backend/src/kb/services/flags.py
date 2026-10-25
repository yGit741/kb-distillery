"""Feature flags at run time: registry value + server-side override (runtime flags only).

Overrides live in `meta/.ops/flags.json` (gitignored, this Mac's server) — never only in a browser.
Only the owner may set one: a PUT must carry `X-KB-Owner-Token` equal to the secret in the macOS keychain
item `kb-flags-owner`. The server reads it with `security`; agents are guard-blocked from the keychain
(`kb.git.git_guard`, SECURITY_BLOCKED) so they cannot learn the token or flip a flag. The item is created
on the first PUT that finds it missing, with a one-time instruction printed to the server log.
"""
from __future__ import annotations

import datetime as dt
import getpass
import hmac
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from kb.flags.registry import FLAGS_TOML, load
from kb.paths import OPS_PATH

OVERRIDES_PATH = Path(OPS_PATH) / "flags.json"
KEYCHAIN_SERVICE = "kb-flags-owner"
ENV = "local"                     # this server is the local app


class FlagRefused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def read_overrides(path: Path | None = None) -> dict[str, dict]:
    path = Path(path or OVERRIDES_PATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict) and isinstance(v.get("value"), bool)}


def list_flags(env: str = ENV, registry_path=FLAGS_TOML, overrides_path: Path | None = None) -> dict:
    reg = load(registry_path)
    ov = read_overrides(overrides_path)
    flags = []
    for f in reg.flags:
        base = f.value(env)
        o = ov.get(f.name) if f.kind == "runtime" else None
        flags.append({
            "name": f.name, "description": f.description, "owner": f.owner,
            "created": f.created.isoformat(), "expires": f.expires.isoformat(), "kind": f.kind,
            "default": f.default, "envs": f.envs.model_dump(), "registry_value": base,
            "value": o["value"] if o else base,
            "source": "override" if o else "registry",
            "overridden_at": o.get("at") if o else None,
        })
    return {"env": env, "flags": flags,
            "overrides": {x["name"]: x["value"] for x in flags if x["source"] == "override"}}


# ---------- owner token (macOS keychain) ----------

def keychain_token() -> str | None:
    """The owner token, or None when the keychain item does not exist (or `security` is unavailable)."""
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                           capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    tok = r.stdout.strip()
    return tok if r.returncode == 0 and tok else None


def create_keychain_token() -> bool:
    tok = secrets.token_urlsafe(32)
    try:
        r = subprocess.run(["security", "add-generic-password", "-s", KEYCHAIN_SERVICE, "-a", getpass.getuser(),
                            "-w", tok], capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode == 0:
        print(f"[flags] created keychain item {KEYCHAIN_SERVICE!r} (first use). To flip flags, read it yourself:\n"
              f"        security find-generic-password -s {KEYCHAIN_SERVICE} -w\n"
              f"        and send it as the X-KB-Owner-Token header. Agents cannot read the keychain.",
              file=sys.stderr)
    return r.returncode == 0


def check_owner(token: str | None, read=None, create=None) -> None:
    read, create = read or keychain_token, create or create_keychain_token
    expected = read()
    if expected is None:
        made = create()
        raise FlagRefused(403, f"owner token created in keychain item {KEYCHAIN_SERVICE!r}; read it with "
                               f"`security find-generic-password -s {KEYCHAIN_SERVICE} -w` and retry"
                          if made else f"no owner token: keychain item {KEYCHAIN_SERVICE!r} missing")
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise FlagRefused(403, "only the owner may set flags (X-KB-Owner-Token missing or wrong)")


def set_override(name: str, value: bool | None, token: str | None, *, registry_path=FLAGS_TOML,
                 overrides_path: Path | None = None, read=None, create=None) -> dict:
    """Set (value bool) or clear (value None) the override of runtime flag `name`; returns list_flags()."""
    reg = load(registry_path)
    try:
        f = reg.get(name)
    except KeyError as e:
        raise FlagRefused(404, str(e.args[0])) from None
    if f.kind != "runtime":
        raise FlagRefused(409, f"{name} is a build flag: it is fixed per bundle, change meta/flags.toml")
    check_owner(token, read, create)
    path = Path(overrides_path or OVERRIDES_PATH)
    ov = read_overrides(path)
    if value is None:
        ov.pop(name, None)
    else:
        ov[name] = {"value": value, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ov, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return list_flags(registry_path=registry_path, overrides_path=path)
