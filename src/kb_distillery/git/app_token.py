"""Agent identity: run gh (and git push) as the `thesis-knowledge-base` GitHub App.

Config `~/.config/kb-agents/app.toml` (override with env `KB_APP_CONFIG`) holds `app_id`,
`installation_id`, `slug`, optional `key_path` (default: `key.pem` beside the toml). The private key
is read only here, at runtime, to sign a 10-minute RS256 JWT, which is exchanged for a 1 h
installation token (POST /app/installations/{id}/access_tokens). The token is cached in
`<root>/.cache/gh-app-token.json` (mode 600, gitignored) and re-minted 5 min before expiry.

No config → every helper falls back to the user's own `gh auth` with a one-line warning, so nothing
breaks before setup. The token is never printed, logged, or written to `.git/config`: gh gets it via
`GH_TOKEN`, git push via a `GIT_ASKPASS` script that echoes an env var.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import stat
import subprocess
import sys
import time
import urllib.request

API = "https://api.github.com"
REFRESH_MARGIN = 300          # seconds before expiry to re-mint
CACHE_NAME = "gh-app-token.json"
_warned = False
_failed = False   # a failed mint is not retried in the same process (no repeated network waits)


def config_path():
    return os.environ.get("KB_APP_CONFIG") or os.path.join(os.path.expanduser("~"), ".config", "kb-agents", "app.toml")


def _parse_toml(text):
    """tomllib (3.11+), else tomli, else a flat `key = value` reader — Stop hooks run on the system python3 (3.9)."""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            tomllib = None
    if tomllib:
        return tomllib.loads(text)
    cfg = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "[")) or "=" not in line:
            continue
        key, val = (x.strip() for x in line.split("=", 1))
        if val[:1] in ("'", '"'):
            end = val.find(val[0], 1)
            cfg[key] = val[1:end] if end > 0 else val[1:]
            continue
        val = val.split("#", 1)[0].strip()
        try:
            cfg[key] = int(val)
        except ValueError:
            cfg[key] = val
    return cfg


def load_config():
    """The App config dict, or None when the file is missing/unreadable/incomplete."""
    path = config_path()
    try:
        with open(path, encoding="utf-8") as f:
            cfg = _parse_toml(f.read())
    except (OSError, ValueError):
        return None
    if not cfg.get("app_id") or not cfg.get("installation_id"):
        return None
    cfg.setdefault("key_path", os.path.join(os.path.dirname(path), "key.pem"))
    cfg["key_path"] = os.path.expanduser(str(cfg["key_path"]))
    return cfg


def owner_login():
    """The user's GitHub login whose Approve review lifts a hold, or None in fallback mode (no App config).

    Env `KB_OWNER_LOGIN` is a fallback only when the toml has no `owner_login` (so an agent cannot
    rename the owner from its own command line); without an App config agents act
    as the user, so no review can be told apart from theirs and only `ship approve` counts."""
    cfg = load_config()
    if cfg is None:
        return None
    return cfg.get("owner_login") or os.environ.get("KB_OWNER_LOGIN") or None


def _jwt(cfg, now=None):
    import jwt  # PyJWT (+ cryptography) ships in the pixi env
    now = int(now if now is not None else time.time())
    with open(cfg["key_path"], "rb") as f:
        key = f.read()
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": str(cfg["app_id"])}, key, algorithm="RS256")


def _http_post(url, headers):
    req = urllib.request.Request(url, data=b"", method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())


def _cache_file(root):
    return os.path.join(root, ".cache", CACHE_NAME)


def _read_cache(root, cfg):
    try:
        with open(_cache_file(root)) as f:
            c = json.load(f)
    except (OSError, ValueError):
        return None
    if str(c.get("installation_id")) != str(cfg["installation_id"]):
        return None
    if float(c.get("expires_epoch", 0)) - REFRESH_MARGIN <= time.time():
        return None
    return c if c.get("token") else None


def _write_cache(root, data):
    path = _cache_file(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _mint(root, cfg):
    url = f"{API}/app/installations/{cfg['installation_id']}/access_tokens"
    resp = _http_post(url, {"Authorization": f"Bearer {_jwt(cfg)}", "Accept": "application/vnd.github+json",
                            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "kb-agents"})
    exp = _dt.datetime.fromisoformat(resp["expires_at"].replace("Z", "+00:00")).timestamp()
    data = {"token": resp["token"], "expires_epoch": exp, "installation_id": cfg["installation_id"],
            "slug": cfg.get("slug", ""), "permissions": resp.get("permissions") or {}}
    _write_cache(root, data)
    return data


def _warn(msg):
    global _warned
    if not _warned:
        print(f"warning: {msg} — gh uses your own auth (user fallback)", file=sys.stderr)
        _warned = True


def token_info(root):
    """Cached-or-fresh {token, expires_epoch, slug, permissions}, or None (no config / minting failed)."""
    cfg = load_config()
    if cfg is None:
        _warn("no GitHub App config")
        return None
    cached = _read_cache(root, cfg)
    if cached:
        return cached
    global _failed
    if _failed:
        return None
    try:
        return _mint(root, cfg)
    except Exception as e:  # network, bad key, HTTP error: never break ship
        _failed = True
        _warn(f"GitHub App token mint failed ({type(e).__name__})")
        return None


def token(root):
    info = token_info(root)
    return info["token"] if info else None


def gh_env(root, base=None):
    """os.environ copy with GH_TOKEN set to the App token (unchanged when falling back)."""
    env = dict(os.environ if base is None else base)
    tok = token(root)
    if tok:
        env["GH_TOKEN"] = tok
        env.pop("GITHUB_TOKEN", None)
    return env


def run_gh(args, root, timeout=None):
    """Run `$GH_BIN args` as the App. Same CompletedProcess contract as subprocess.run(capture_output)."""
    exe = os.environ.get("GH_BIN", "gh")
    return subprocess.run([exe, *args], cwd=root, capture_output=True, text=True, check=False,
                          timeout=timeout, env=gh_env(root))


ASKPASS = """#!/bin/sh
case "$1" in
  Username*) echo x-access-token ;;
  *) echo "$KB_GIT_TOKEN" ;;
esac
"""


def _https_origin(root):
    cp = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True, check=False)
    return cp.returncode == 0 and cp.stdout.strip().startswith("https://")


def git_push_cmd(root):
    """(git argv prefix, env) for a push as the App, or None to push with the user's credentials.

    Only when the installation token has `contents: write`. The token stays in env (`KB_GIT_TOKEN`);
    the askpass script holds no secret. `-c credential.helper=` keeps keychain helpers out of it."""
    if not _https_origin(root):
        return None
    info = token_info(root)
    if not info or (info.get("permissions") or {}).get("contents") != "write":
        return None
    script = os.path.join(root, ".cache", "gh-askpass.sh")
    os.makedirs(os.path.dirname(script), exist_ok=True)
    if not os.path.exists(script) or open(script).read() != ASKPASS:
        with open(script, "w") as f:
            f.write(ASKPASS)
    os.chmod(script, 0o700)
    env = dict(os.environ, GIT_ASKPASS=script, KB_GIT_TOKEN=info["token"], GIT_TERMINAL_PROMPT="0")
    return ["git", "-c", "credential.helper="], env


def run_git_push(args, cwd):
    """`git <args>` (a push) as the App when it may write contents, else as the user."""
    spec = git_push_cmd(cwd)
    if spec is None:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    prefix, env = spec
    cp = subprocess.run([*prefix, *args], cwd=cwd, capture_output=True, text=True, check=False, env=env)
    err = (cp.stderr or "").lower()
    if cp.returncode != 0 and any(k in err for k in ("returned error: 403", "authentication failed", "permission to")):
        print("warning: push as the GitHub App was refused — retrying with your own credentials", file=sys.stderr)
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return cp


def whoami(root):
    """One line: which identity gh calls will use."""
    info = token_info(root)
    if not info:
        return "user fallback (gh auth of the logged-in user)"
    slug = info.get("slug") or "app"
    left = int((float(info["expires_epoch"]) - time.time()) // 60)
    push = "app" if git_push_cmd(root) else "user"
    return f"{slug}[bot] (installation token, {left} min left; git push as {push})"
