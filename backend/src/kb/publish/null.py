"""The publisher used when none is configured: reports it, publishes nothing."""
from __future__ import annotations

from typing import Optional

from .base import NotConfigured, PublishResult, Publisher, Snapshot

DEFAULT_REASON = "no publisher configured: set [publish] publisher in kb.toml (or $KB_PUBLISHER)"


class NullPublisher(Publisher):
    name = "none"

    def __init__(self, root: Optional[str] = None, reason: str = DEFAULT_REASON, **options):
        super().__init__(root, **options)
        self.reason = reason

    def available(self) -> bool:
        return False

    def status(self, root: Optional[str] = None) -> Optional[dict]:
        return None

    def publish(self, snapshot: Snapshot, *, dry_run: bool = False) -> PublishResult:
        raise NotConfigured(self.reason)

    def log_tail(self, n: int = 200) -> str:
        return "no publisher configured\n"
