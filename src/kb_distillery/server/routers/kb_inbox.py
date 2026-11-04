"""GET /api/kb/inbox and POST /api/kb/inbox/pull: the deployed site's upload inbox, as `distill kb inbox list` / `pull`.

The site and token come from `kb_distillery.inbox` (env or keychain). Missing set-up is `configured: false`, not an
error, so the app can show a hint; an unreachable site or a refused token is `error`. `pull` imports every pending
upload as a new kb on this Mac and reports each outcome back to the site.
"""
import functools
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

from kb_distillery import inbox
from kb_distillery.server.models.kb_inbox import KbInbox, KbInboxOutcome, KbInboxPull

router = APIRouter(tags=["kb"])

GUIDE = "docs/guides/import-a-bundle.md"
_GITHUB = re.compile(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


@functools.lru_cache(maxsize=1)
def guide_url() -> str:
    """The set-up guide on GitHub, from this checkout's origin remote; empty when there is none (an installed wheel)."""
    root = Path(__file__).resolve().parents[4]
    if not (root / GUIDE).is_file():
        return ""
    try:
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = _GITHUB.match(remote.strip())
    return f"https://github.com/{m.group(1)}/{m.group(2)}/blob/main/{GUIDE}#from-the-site-inbox" if m else ""


@router.get("/api/kb/inbox", response_model=KbInbox, summary="Uploads waiting on the site's inbox")
def get_inbox():
    try:
        return {"configured": True, "items": inbox.Client().items("all")}
    except inbox.NotConfigured:
        return {"configured": False, "guide": guide_url()}
    except inbox.InboxError as e:
        return {"configured": True, "error": str(e)}


@router.post("/api/kb/inbox/pull", response_model=KbInboxPull, summary="Import every pending upload as a new knowledge base")
def pull_inbox():
    try:
        result = inbox.pull(inbox.Client(), out=lambda *_: None)
    except inbox.NotConfigured as e:
        raise HTTPException(409, str(e)) from None
    except inbox.InboxError as e:
        raise HTTPException(502, str(e)) from None
    return {
        "imported": [KbInboxOutcome(item=i, kb_id=k) for i, k in result.imported],
        "failed": [KbInboxOutcome(item=i, error=e) for i, e in result.failed],
        "unreported": result.unreported,
    }
