"""distill kb inbox: pick up the uploads parked in the deployed site's inbox and import them on this Mac.

    distill kb inbox list [--status pending|imported|failed|all] [--json]
    distill kb inbox pull [--dir PARENT] [--dry-run]

A signed-in owner uploads an OKF bundle (a zip, or a git URL) to the private site; the Worker checks it and stores it in
its R2 inbox as `pending` (`publish/cloudflare/worker/inbox.js`). `pull` fetches the pending items, runs
`import_kb.import_bundle` on each (a NEW kb under the bases dir, never published) and reports the outcome back to the site:
`imported` with the new kb id, or `failed` with the error. A git URL is only a record on the site; this Mac clones it.
One bad item never stops the others, and nothing is imported twice: only `pending` items are fetched.

Site and credentials:
  - the site: `$KB_INBOX_URL`, else the `url` in the configured publisher's last publish status (the private site the
    deploy owner last deployed). Only https (or http://localhost) is accepted: the token travels in a header.
  - the token: `$KB_INBOX_TOKEN`, else the macOS keychain item `kb-inbox-token` (the Worker holds the same value as its
    secret `INBOX_TOKEN`). It is never printed and never put in a URL; set-up is in `docs/guides/import-a-bundle.md`.
No redirect is followed (a redirect would carry the token elsewhere).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote, urlparse

KEYCHAIN_SERVICE = "kb-inbox-token"
ENV_URL, ENV_TOKEN = "KB_INBOX_URL", "KB_INBOX_TOKEN"
TIMEOUT = 60
MAX_ERROR = 400
STATUSES = ("pending", "imported", "failed")


class InboxError(Exception):
    """The site could not be reached or refused; the message says what to fix (it never holds the token)."""


# ---------- site and token ----------

def site_url() -> str:
    url = (os.environ.get(ENV_URL) or "").strip()
    if not url:
        try:            # the configured publisher's live site, from its last publish (core asks the registry, never a publisher)
            from kb_distillery import hosting
            url = ((hosting.current().status() or {}).get("url") or "").strip()
        except Exception:                                   # noqa: BLE001 — no publisher / no status yet: say how to set it
            url = ""
    if not url:
        raise InboxError(f"no site to ask: set ${ENV_URL} (https://<your-site>) or publish the site once so the publisher's status has its url")
    parsed = urlparse(url)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise InboxError(f"${ENV_URL} must be an https:// URL (the token is sent in a header), got {parsed.scheme or 'none'}://")
    return url.rstrip("/")


def keychain_token() -> str | None:
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                           capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    tok = r.stdout.strip()
    return tok if r.returncode == 0 and tok else None


def token(read: Callable[[], str | None] | None = None) -> str:
    tok = (os.environ.get(ENV_TOKEN) or "").strip() or (read or keychain_token)()
    if not tok:
        raise InboxError(f"no inbox token: set ${ENV_TOKEN} or add the macOS keychain item {KEYCHAIN_SERVICE!r} "
                         "(docs/guides/import-a-bundle.md, owner set-up)")
    return tok


# ---------- HTTP (the seam tests replace) ----------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http(method: str, url: str, tok: str, body: dict | None = None) -> tuple[int, bytes]:
    """(status, body bytes) of one call with the bearer token; (0, b"") when the site is unreachable. No redirects."""
    from kb_distillery.config import net
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/json", "User-Agent": "kb-distillery-inbox"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=net.ssl_context()), _NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=TIMEOUT) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, b""


class Client:
    def __init__(self, base: str | None = None, tok: str | None = None, request: Callable = http):
        self.base, self.tok, self.request = base or site_url(), tok or token(), request

    def call(self, method: str, path: str, body: dict | None = None) -> bytes:
        status, raw = self.request(method, self.base + path, self.tok, body)
        if status == 0:
            raise InboxError(f"cannot reach {self.base}")
        if status in (401, 403):
            raise InboxError(f"the site refused the inbox token ({status}): check ${ENV_TOKEN} / keychain {KEYCHAIN_SERVICE!r} "
                             "against the Worker secret INBOX_TOKEN")
        if status == 503:
            raise InboxError("the site's inbox is not set up: create the R2 bucket and bind it as KB_INBOX (docs/guides/import-a-bundle.md)")
        if not 200 <= status < 300:
            raise InboxError(f"the site answered {status} for {method} {path}")
        return raw

    def items(self, status: str = "pending") -> list[dict]:
        path = "/api/inbox" + ("" if status == "all" else f"?status={quote(status)}")
        try:
            return list(json.loads(self.call("GET", path)).get("items") or [])
        except ValueError:
            raise InboxError("the site's inbox answered something that is not JSON") from None

    def bundle(self, item: str) -> bytes:
        return self.call("GET", f"/api/inbox/{quote(item)}/bundle")

    def report(self, item: str, **body) -> None:
        self.call("POST", f"/api/inbox/{quote(item)}/status", body)


# ---------- pull ----------

@dataclass
class PullResult:
    imported: list[tuple[str, str]] = field(default_factory=list)       # (item, new kb id)
    failed: list[tuple[str, str]] = field(default_factory=list)         # (item, error)
    unreported: list[str] = field(default_factory=list)                 # imported/failed here, but the site did not take the news

    @property
    def ok(self) -> bool:
        return not self.failed and not self.unreported


def _report(client: Client, item: str, **body) -> bool:
    """Tell the site the outcome; one retry. False when it still would not take it (the item stays pending there)."""
    for _ in range(2):
        try:
            client.report(item, **body)
            return True
        except InboxError as e:
            last = e
    print(f"warning: could not report {item} to the site: {last}", file=sys.stderr)
    return False


def pull(client: Client | None = None, parent: str | None = None, dry_run: bool = False, out=print,
         importer: Callable | None = None) -> PullResult:
    """Import every pending item as a new kb under `parent` (the bases dir) and report each outcome to the site."""
    from kb_distillery import import_kb
    client = client or Client()
    importer = importer or import_kb.import_bundle
    result = PullResult()
    for it in sorted(client.items("pending"), key=lambda i: i.get("item", "")):
        item = it["item"]
        want = it.get("kb_id") or None
        if dry_run:
            out(f"would import {item} ({it.get('kind')}) as {want or '<derived>'}")
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="kb-inbox-") as tmp:
                if it.get("kind") == "git":
                    source = it["git_url"]
                else:
                    source = os.path.join(tmp, f"{want or 'bundle'}.zip")
                    with open(source, "wb") as f:
                        f.write(client.bundle(item))
                target = importer(source, kit=it.get("kit") or None, kb_id=want, parent=parent)
        except Exception as e:                                  # noqa: BLE001 — one bad item must not stop the rest
            error = (str(e) or type(e).__name__).strip()[:MAX_ERROR]
            out(f"failed {item}: {error.splitlines()[0]}")
            result.failed.append((item, error))
            if not _report(client, item, status="failed", error=error):
                result.unreported.append(item)
            continue
        kb_id = os.path.basename(str(target).rstrip("/"))
        out(f"imported {item} -> {kb_id} ({target})")
        result.imported.append((item, kb_id))
        if not _report(client, item, status="imported", kb_id=kb_id):
            result.unreported.append(item)
    if not result.imported and not result.failed and not dry_run:
        out("inbox is empty: nothing pending")
    return result


# ---------- CLI ----------

def _list(args) -> int:
    items = Client().items(args.status)
    if args.json:
        print(json.dumps(items, indent=2))
        return 0
    if not items:
        print(f"no {args.status if args.status != 'all' else ''} items in the inbox".replace("  ", " "))
        return 0
    for i in items:
        what = i.get("git_url") if i.get("kind") == "git" else f"{i.get('pages', 0)} page(s)"
        print(f"{i['item']}  {i.get('status', '?'):<8} {i.get('kind', '?'):<3} {i.get('kb_id') or '-':<20} "
              f"{i.get('uploader', '?')}  {what}" + (f"  error: {i['error']}" if i.get("error") else ""))
    return 0


def _pull(args) -> int:
    return 0 if pull(parent=args.dir, dry_run=args.dry_run).ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="distill kb inbox", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list", help="what is in the site's inbox")
    ls.add_argument("--status", choices=[*STATUSES, "all"], default="pending")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(fn=_list)
    pl = sub.add_parser("pull", help="import every pending item as a new kb, then report back to the site")
    pl.add_argument("--dir", help="parent folder for the new kbs (default: the bases dir, ~/knowledge)")
    pl.add_argument("--dry-run", action="store_true", help="list what would be imported; import and report nothing")
    pl.set_defaults(fn=_pull)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except InboxError as e:
        print(f"distill kb inbox: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
