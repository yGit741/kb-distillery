"""The one reader of the share config: who may sign in, the Cloudflare account, the log file and the Home tour.

Nothing personal is tracked. The first file that exists is the config, in this order:

1. `$KB_SHARE_CONFIG` (a path; if it is set and missing that is an error, not a fall-through)
2. `<kb>/.cache/share/share.toml` (the knowledge base being shared; untracked)
3. `~/.config/kb-distillery/share.toml` (yours, for every knowledge base)
4. `share.example.toml` beside this module: placeholders only. It fills in keys the found file leaves out
   (like `compatibility_date`) but is never a config by itself: `require()` refuses without a real file.

A few values also have an environment override, which wins over the file: `KB_SHARE_GOOGLE_CLIENT_ID`,
`KB_SHARE_FLAGS_KV_ID`, `KB_CLOUDFLARE_SUBDOMAIN`, `KB_CLOUDFLARE_ACCOUNT_ID`.

Imports only `kb_distillery.config`, so `contracts` can read the subdomain and log path at import.
"""
from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Optional

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import userdir

ENV_FILE = "KB_SHARE_CONFIG"
FILE_NAME = "share.toml"
EXAMPLE = Path(__file__).resolve().parent / "share.example.toml"
DEFAULT_COMPAT = "2026-09-01"
DEFAULT_LOG = "~/Library/Logs/kb-distillery-share.log"


class ShareConfigError(Exception):
    """The share config is missing or unreadable; the message names the files and what to do."""


def user_path() -> Path:
    return Path(userdir.path(FILE_NAME))


def kb_path(root: Optional[str] = None) -> Path:
    return Path(root or kbconfig.vault_root()) / ".cache" / "share" / FILE_NAME


def candidates(root: Optional[str] = None) -> list[tuple[str, Path]]:
    """(where, path) in read order, without the example."""
    out = []
    if os.environ.get(ENV_FILE):
        out.append(("$" + ENV_FILE, Path(os.environ[ENV_FILE]).expanduser()))
    out += [("knowledge base", kb_path(root)), ("user", user_path())]
    return out


def find(root: Optional[str] = None) -> Optional[Path]:
    """The config file in use, None when there is none. A set but missing `$KB_SHARE_CONFIG` is not skipped."""
    for where, p in candidates(root):
        if p.is_file():
            return p
        if where.startswith("$"):
            return None
    return None


def _read(path: Path) -> dict:
    try:
        return tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise ShareConfigError(f"share config unreadable: {path} ({e.strerror or e})") from None
    except tomllib.TOMLDecodeError as e:
        raise ShareConfigError(f"share config unreadable: {path} ({e}) — fix the TOML, then try again") from None


def load(path: Optional[Path] = None, root: Optional[str] = None) -> dict:
    """The config as sections: the example's keys, overlaid by `path` or else by the file in use."""
    data = _read(EXAMPLE)
    found = Path(path) if path else find(root)
    if found is not None:
        for section, table in _read(found).items():
            if isinstance(table, dict) and isinstance(data.get(section), dict):
                data[section].update(table)
            else:
                data[section] = table
    return data


def write_path(root: Optional[str] = None) -> Path:
    """Where `share config` stores values: the file in use, `$KB_SHARE_CONFIG` when it is set (even if not there yet),
    else the user file."""
    if os.environ.get(ENV_FILE):
        return Path(os.environ[ENV_FILE]).expanduser()
    return find(root) or user_path()


def require(root: Optional[str] = None) -> Path:
    """The config file in use; ShareConfigError, naming where to put one, when there is none."""
    found = find(root)
    if found is not None:
        return found
    places = "\n".join(f"  {where}: {p}" for where, p in candidates(root))
    raise ShareConfigError(f"no share config found. Looked for, in this order:\n{places}\n"
                           f"Copy {EXAMPLE} to one of them and fill it in (the build reads the Home tour and cards from it; "
                           "a deploy also needs the Google client id, allowed emails and workers.dev subdomain).")


def settings(path: Optional[Path] = None, root: Optional[str] = None) -> dict:
    """{google_client_id, allowed_emails, compatibility_date, flags_kv_id} for the Worker, env overrides applied."""
    data = load(path, root)
    auth, worker = data.get("auth") or {}, data.get("worker") or {}
    return {
        "google_client_id": os.environ.get("KB_SHARE_GOOGLE_CLIENT_ID") or auth.get("google_client_id") or "",
        "allowed_emails": list(auth.get("allowed_emails") or []),
        "compatibility_date": worker.get("compatibility_date") or DEFAULT_COMPAT,
        # KV namespace for runtime flag overrides; empty means not bound
        "flags_kv_id": os.environ.get("KB_SHARE_FLAGS_KV_ID") or worker.get("flags_kv_id") or "",
    }


def _lenient(root: Optional[str] = None) -> dict:
    try:
        return load(root=root)
    except Exception:  # noqa: BLE001  (read at import by contracts: a broken file or kb must not break importing the publisher)
        return {}


def subdomain(root: Optional[str] = None) -> str:
    """The workers.dev account subdomain; "" when unset (a deploy then refuses, see `check_deploy`)."""
    return os.environ.get("KB_CLOUDFLARE_SUBDOMAIN") or str((_lenient(root).get("cloudflare") or {}).get("subdomain") or "")


def account_id(root: Optional[str] = None) -> str:
    """The Cloudflare account id (not secret); "" when unset (a deploy and the panel then refuse)."""
    return os.environ.get("KB_CLOUDFLARE_ACCOUNT_ID") or str((_lenient(root).get("cloudflare") or {}).get("account_id") or "")


def log_path(root: Optional[str] = None) -> Path:
    return Path(str((_lenient(root).get("share") or {}).get("log_path") or DEFAULT_LOG)).expanduser()


def home(path: Optional[Path] = None, root: Optional[str] = None) -> dict:
    """`[home]` as {cards: [...], tour: str|None}."""
    table = load(path, root).get("home") or {}
    cards = [c for c in table.get("cards") or [] if isinstance(c, dict) and c.get("title") and c.get("pages")]
    tour = table.get("tour") if isinstance(table.get("tour"), str) and table.get("tour") else None
    return {"cards": cards, "tour": tour}


def check_deploy(cfg: dict, require_access: bool = True, account_subdomain: Optional[str] = None) -> None:
    """Refuse a deploy that would publish a site nobody can reach or a link that points nowhere."""
    missing = []
    if not (subdomain() if account_subdomain is None else account_subdomain):
        missing.append("[cloudflare] subdomain (or KB_CLOUDFLARE_SUBDOMAIN)")
    if require_access:
        if not account_id():
            missing.append("[cloudflare] account_id (or KB_CLOUDFLARE_ACCOUNT_ID)")
        if not cfg.get("google_client_id"):
            missing.append("[auth] google_client_id (or KB_SHARE_GOOGLE_CLIENT_ID)")
        if not cfg.get("allowed_emails"):
            missing.append("[auth] allowed_emails")
    if missing:
        raise ShareConfigError("share config incomplete, a deploy needs: " + ", ".join(missing)
                               + f". Put them in {user_path()} (template: {EXAMPLE}).")


def set_values(text: str, section: str, values: dict[str, str]) -> str:
    """`text` with `key = literal` set inside `[section]` (added when missing), every other line untouched.
    The literals are TOML source, e.g. json.dumps("x") or '["a", "b"]'."""
    lines = text.splitlines()
    header = re.compile(rf"^\s*\[{re.escape(section)}\]\s*(#.*)?$")
    start = next((i for i, ln in enumerate(lines) if header.match(ln)), None)
    if start is None:
        lines += ([""] if lines and lines[-1].strip() else []) + [f"[{section}]"]
        start = len(lines) - 1
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^\s*\[", lines[i])), len(lines))
    for key, literal in values.items():
        pat = re.compile(rf"^\s*{re.escape(key)}\s*=")
        at = next((i for i in range(start + 1, end) if pat.match(lines[i])), None)
        if at is None:
            put = end
            while put - 1 > start and not lines[put - 1].strip():
                put -= 1
            lines.insert(put, f"{key} = {literal}")
            end += 1
        else:
            lines[at] = f"{key} = {literal}"
    return "\n".join(lines) + "\n"
