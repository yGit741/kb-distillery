"""The publisher interface: how a knowledge base is published as a site, kept outside core.

Core never imports a publisher's code. It asks `kb_distillery.publish.current()` for a `Publisher` and calls the methods below;
what is behind them (Cloudflare, a static host, nothing) is the publisher's business.

    available()               pure local check: can this publisher publish right now (credentials, tools)? never raises
    status(root)              the last publish outcome as a dict (keys in STATUS_KEYS), or None when nothing was published
    publish(snapshot)         publish a snapshot (`Snapshot("main")` = the live site, a named one = a public snapshot)
    log_tail(n)               the last n lines of the publisher's log, for the log page
    request_publish(reason)   ask the publisher to publish main soon (a nudge, may do nothing); never raises
    rollback(to)              back to the previous (or a given) published version
    snapshots()               the published snapshots, one dict each
    orphan_snapshots()        names of published snapshots that have no reachable record (read-only)
    audit(ref)                what publishing `ref` publicly would expose
    account_api()             an authenticated client for the publisher's cloud account (only some publishers have one)

Only `available`, `status` and `publish` are required; the rest default to "nothing / not supported" so a small
publisher stays small. `tests/publish/test_publisher_contract.py` is the suite every publisher must pass.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Optional

STATUS_KEYS = ("state", "sha", "kb_version", "at", "error", "url")


class PublishError(Exception):
    """A publisher could not do what was asked; the message says what to change."""


class NotSupported(PublishError):
    """This publisher does not offer that operation (rollback, snapshots, ...)."""


class NotConfigured(PublishError):
    """No publisher is selected for this kb."""


@dataclass(frozen=True)
class Snapshot:
    """What to publish. `ref` is a git ref (main, a commit, kb-x.y.z). No name = the live site (private);
    a name = a named snapshot, public when `public` is true. `options` carries publisher specific switches."""
    ref: str = "main"
    name: Optional[str] = None
    public: bool = False
    options: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class PublishResult:
    """Outcome of one publish or rollback. `state` is one of the publisher's own states (the Cloudflare one uses
    deployed, skipped-same, skipped-older, refused-no-access, failed)."""
    state: str
    url: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None


class Publisher(ABC):
    name: ClassVar[str] = ""

    def __init__(self, root: Optional[str] = None, **options):
        self.root = root
        self.options = options

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def status(self, root: Optional[str] = None) -> Optional[dict]: ...

    @abstractmethod
    def publish(self, snapshot: Snapshot, *, dry_run: bool = False) -> PublishResult: ...

    def log_tail(self, n: int = 200) -> str:
        return "no publish log yet\n"

    def request_publish(self, reason: str = "", root: Optional[str] = None, foreground: bool = False) -> str:
        """Returns a short word for what happened (nudged, disabled, ...). Must not raise for ordinary failures."""
        return "disabled"

    def rollback(self, to: Optional[str] = None) -> PublishResult:
        raise NotSupported(f"publisher {self.name!r} cannot roll back")

    def snapshots(self) -> list[dict]:
        return []

    def orphan_snapshots(self) -> list[str]:
        return []

    def audit(self, ref: str) -> dict:
        raise NotSupported(f"publisher {self.name!r} cannot audit a snapshot")

    def account_api(self):
        raise NotSupported(f"publisher {self.name!r} has no cloud account API")


def read_status_file(path) -> Optional[dict]:
    """A publisher status file (JSON with the STATUS_KEYS) as a dict, or None when missing or unreadable.
    The format is part of the contract, so core can read a file it was handed without a publisher."""
    import json
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return {k: data.get(k) for k in STATUS_KEYS} if isinstance(data, dict) else None
