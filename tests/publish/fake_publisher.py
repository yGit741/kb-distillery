"""A publisher that keeps everything in memory: stands in for a third-party package in the contract and registry tests."""
from kb_distillery.publish import PublishResult, Publisher, Snapshot


class MemoryPublisher(Publisher):
    name = "memory"

    def __init__(self, root=None, **options):
        super().__init__(root, **options)
        self.published = []
        self.nudges = []

    def available(self):
        return True

    def status(self, root=None):
        if not self.published:
            return None
        ref = self.published[-1].ref
        return {"state": "deployed", "sha": ref, "kb_version": "0.0.1", "at": "2026-01-01T00:00:00+00:00",
                "error": None, "url": "https://example.test/"}

    def publish(self, snapshot: Snapshot, *, dry_run=False):
        if not dry_run:
            self.published.append(snapshot)
        return PublishResult("deployed", url="https://example.test/", version=str(len(self.published)))

    def request_publish(self, reason="", root=None, foreground=False):
        self.nudges.append(reason)
        return "nudged"
