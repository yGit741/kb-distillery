"""Client for the local qmd service (`tools/qmd/server.mjs`): meaning-based hits over the summary cards.

Never raises and never waits long: when the service is down, busy (503) or slow, the app just shows
keyword results.
"""
import json
import os
import re
import urllib.parse
import urllib.request

PORT = int(os.environ.get("KB_QMD_PORT", "8766"))
BASE = f"http://127.0.0.1:{PORT}"


def _get(path, timeout):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def qmd_key(slug):
    """How qmd names a card file: every run of non letters/digits becomes '-' (dots included)."""
    return re.sub(r"[\W_]+", "-", slug).strip("-")


def search(query, limit=10, mode="fast", timeout=1.5):
    """[(qmd key, score)] best first, or None when the service is unavailable, busy or too slow.
    mode fast = BM25 + vectors, no LLM (the search box); deep = + query expansion and re-ranking.
    Keys are `qmd_key(slug)`; map them back with a {qmd_key(s): s} table."""
    q = urllib.parse.urlencode({"q": query, "limit": limit, "mode": mode})
    try:
        data = _get(f"/search?{q}", timeout)
        return [(str(h["slug"]), float(h.get("score") or 0)) for h in data["hits"] if h.get("slug")]
    except Exception:                    # down, 503, timeout, torn response, unexpected JSON
        return None


def health(timeout=1.0):
    try:
        data = _get("/health", timeout)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def refresh(timeout=1.0):
    """Ask the service to re-index changed cards (it answers at once; it also refreshes every 10 min)."""
    req = urllib.request.Request(BASE + "/refresh", method="POST", data=b"", headers={"X-KB-Refresh": "1"})
    try:
        urllib.request.urlopen(req, timeout=timeout).close()
        return True
    except Exception:
        return False
