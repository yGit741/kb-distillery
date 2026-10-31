"""The Cloudflare publisher: `kb.publish.Publisher` over the share code in this package.

Selected by `[publish] publisher = "cloudflare"` in kb.toml (or `$KB_PUBLISHER=cloudflare`); nothing selects it by default.
Every method delegates to the module that already did the work (`deploy`, `snapshots`, `owner`, `autodeploy`, `cf_api`,
`contracts`), looked up when called, so the behaviour is what `pixi run share -- ...` and the old direct calls gave.

`seams` (a constructor keyword, for tests) is passed to `deploy.deploy_main` / `deploy.rollback`: `runner`, `http`, ...
so a test never runs wrangler.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

from kb.publish import PublishError, PublishResult, Publisher, Snapshot

LOG_LINES = 200


def _result(r) -> PublishResult:
    return PublishResult(r.state, url=r.url, version=r.version_id, error=r.error)


class _Account:
    """The Cloudflare account's REST API for core's D1 metrics store: `account_id` and `rest(method, path, body)`."""

    @property
    def account_id(self) -> str:
        from kb.share import cf_api
        return cf_api.ACCOUNT_ID

    def rest(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        from kb.share import cf_api
        return cf_api._rest(method, path, body)


class CloudflarePublisher(Publisher):
    name = "cloudflare"

    def __init__(self, root: Optional[str] = None, *, seams: Optional[dict] = None, **options):
        super().__init__(root, **options)
        self.seams = dict(seams or {})

    def available(self) -> bool:
        """Credentials are present (CLOUDFLARE_API_TOKEN or wrangler's login). A local read: nothing is refreshed."""
        try:
            from kb.share import cf_api
            return bool(os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
                        or str(cf_api._read_wrangler_config().get("oauth_token") or "").strip())
        except Exception:  # noqa: BLE001
            return False

    def status(self, root: Optional[str] = None) -> Optional[dict]:
        from kb.share import contracts
        if root is None:
            return contracts.StatusFile().read()
        return contracts.StatusFile(Path(root) / ".cache" / "share" / "status.json").read()

    def publish(self, snapshot: Snapshot, *, dry_run: bool = False) -> PublishResult:
        if snapshot.name is None:
            if snapshot.ref != "main":
                raise PublishError("the live site is always built from main; give the snapshot a name to publish another ref")
            from kb.share import deploy
            return _result(deploy.deploy_main(force=bool(snapshot.options.get("force")), dry_run=dry_run,
                                              app=not snapshot.options.get("legacy"), **self.seams))
        from kb.share import snapshots
        o = snapshot.options
        args = argparse.Namespace(name=snapshot.name, ref=snapshot.ref, replace=bool(o.get("replace")),
                                  force=bool(o.get("force")), allow_flags=bool(o.get("allow_flags")), dry_run=dry_run,
                                  scope=o.get("scope"), hops=o.get("hops", 1), predicate=o.get("predicate"),
                                  view=o.get("view"), app=bool(o.get("app")), viewer_worktree=False)
        rc = snapshots.cmd_snapshot(args)       # prints its report; the exit code is all it returns
        return PublishResult("deployed" if rc == 0 else "failed", error=None if rc == 0 else f"snapshot exited {rc}")

    def log_tail(self, n: int = LOG_LINES) -> str:
        try:
            from kb.share import contracts
            with open(contracts.LOG_PATH, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:  # noqa: BLE001
            return "no share log yet\n"
        return "".join(lines[-n:]) or "share log is empty\n"

    def request_publish(self, reason: str = "", root: Optional[str] = None, foreground: bool = False) -> str:
        """Nudge the deploy owner; `KB_SHARE_DIRECT=1` (the user only) keeps the old direct `deploy-main`."""
        root = root or self.root
        if os.environ.get("KB_SHARE_DIRECT") != "1":
            from kb.share import owner
            return owner.nudge(reason, root)
        from kb.share import autodeploy
        if foreground:
            return str(autodeploy.run_foreground(reason, root))
        return autodeploy.trigger(reason, root)

    def rollback(self, to: Optional[str] = None) -> PublishResult:
        from kb.share import deploy
        from kb.share.contracts import WORKER_MAIN
        return _result(deploy.rollback(WORKER_MAIN, to, **self.seams))

    def snapshots(self) -> list[dict]:
        from kb.share import snapshots
        return snapshots.list_snapshots()

    def orphan_snapshots(self) -> list[str]:
        """Snapshot Workers without a reachable manifest; [] when Cloudflare cannot be asked (offline, no login)."""
        from kb.share import cf_api, snapshots
        try:
            return list(snapshots.prune_plan().get("orphans", []))
        except (cf_api.CloudflareError, OSError):
            return []

    def audit(self, ref: str) -> dict:
        from kb.share import snapshots
        report, _build_dir, tmp = snapshots.audit_build(ref)
        with tmp:
            return report

    def account_api(self):
        return _Account()
