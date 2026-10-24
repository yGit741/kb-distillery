"""Contracts between the share build, deploy and snapshots steps.

Later modules must honour these, not redefine them:

- `Profile` — which content set the build renders (`private` = everything, `public` = shareable).
- `Manifest` — what a build is: content ref + sha + knowledge version, viewer (tooling) sha,
  profile, sha256 of the HTML, `built_at` = the *content commit's* date (ISO 8601), so the same
  content always yields the same manifest. `to_json()` is byte-stable (sorted keys).
- `BuildResult` — a build output directory plus its manifest.
- `DeployState` / `DeployResult` — the outcome of one deploy attempt.
- `StatusFile` — the last deploy outcome at `.cache/share/status.json`, written atomically.
- Worker naming: `WORKER_MAIN` is the live site; snapshots are `snapshot_worker_name(name, date)`.
- Paths: `CACHE_DIR` (build cache + status), `EXPORT_DIR` (user-facing HTML), `LOG_PATH`.
"""
import datetime as _dt
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Optional

from kb.paths import CHECKOUT_ROOT

REPO = Path(CHECKOUT_ROOT)   # the checkout this tool runs from (never $KB_ROOT)

Profile = Literal["private", "public"]
PROFILES = ("private", "public")

DeployState = Literal["deployed", "skipped-same", "skipped-older", "refused-no-access", "failed"]
DEPLOY_STATES = ("deployed", "skipped-same", "skipped-older", "refused-no-access", "failed")

# Correspondence with other people is the one source kind that never goes public: a page whose `raw:`
# (a string or a list) points under this prefix, or a prose mention of such a path, is email-derived.
EMAIL_RAW_PREFIX = "raw/emails/"


def raw_is_email(raw) -> bool:
    """True when a `raw:` frontmatter value (string or list) names a file under raw/emails/."""
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    return any(isinstance(r, str) and r.strip().strip("`'\"").startswith(EMAIL_RAW_PREFIX) for r in items)


WORKER_MAIN = "kb"
ACCOUNT_SUBDOMAIN = "yonatan-magen-thesis"
SNAPSHOT_PREFIX = "snapshot-"
DEPLOY_MESSAGE_PREFIX = "kb-share"
WRANGLER_VERSION = "4.151.3"

LOG_PATH = Path.home() / "Library" / "Logs" / "thesis-kb-share.log"
CACHE_DIR = REPO / ".cache" / "share"
EXPORT_DIR = REPO / ".exported" / "share"
STATUS_PATH = CACHE_DIR / "status.json"

WORKER_NAME_MAX = 63
_WORKER_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


@dataclass
class Manifest:
    content_ref: str
    content_sha: str
    kb_version: str
    viewer_sha: str
    profile: str
    sha256: str
    built_at: str  # ISO 8601, the content commit's date
    # "legacy" = one index.html shell (the default); "app" = the React app build: index.html + assets/,
    # `sha256` is then the digest of the whole tree (build.tree_digest). Left out of the JSON when
    # legacy, so legacy manifests stay byte-identical.
    layout: str = "legacy"

    def to_json(self) -> str:
        d = asdict(self)
        if d["layout"] == "legacy":
            del d["layout"]
        return json.dumps(d, sort_keys=True, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Manifest":
        return cls(**json.loads(text))


@dataclass
class BuildResult:
    dir: Path
    manifest: Manifest


@dataclass
class DeployResult:
    state: str  # DeployState
    url: Optional[str] = None
    version_id: Optional[str] = None
    error: Optional[str] = None


class StatusFile:
    """`.cache/share/status.json`: {state, sha, kb_version, at, error, url} of the last deploy."""

    KEYS = ("state", "sha", "kb_version", "at", "error", "url")

    def __init__(self, path: Path = STATUS_PATH):
        self.path = Path(path)

    def read(self) -> Optional[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        return {k: data.get(k) for k in self.KEYS}

    def write(self, state: str, sha: str, kb_version: str, at: str,
              error: Optional[str] = None, url: Optional[str] = None) -> dict:
        data = {"state": state, "sha": sha, "kb_version": kb_version, "at": at,
                "error": error, "url": url}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".status-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data, sort_keys=True, indent=2) + "\n")
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
        return data


def snapshot_worker_name(name: str, date: _dt.date) -> str:
    """`snapshot-YYYYMMDD-<name>`; raises ValueError with the reason when illegal."""
    if not name:
        raise ValueError("snapshot name is empty")
    if name == WORKER_MAIN:
        raise ValueError(f"snapshot name {name!r} is reserved for the live worker")
    if not name.isascii() or not _WORKER_NAME.match(name):
        raise ValueError(f"snapshot name {name!r} must be lowercase [a-z0-9-] and not start or end with '-'")
    full = f"{SNAPSHOT_PREFIX}{date.strftime('%Y%m%d')}-{name}"
    if len(full) > WORKER_NAME_MAX:
        raise ValueError(f"worker name {full!r} is {len(full)} chars; max {WORKER_NAME_MAX}")
    return full
