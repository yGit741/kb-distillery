"""Routes of the Ops tab, dispatched from serve.Handler.do_GET by one line:

    /ops                 the page
    /api/ops             snapshot JSON (?refresh=1 reruns the checks)
    /ops/email-preview   the exact HTML of tonight's mail
"""
import json
import os

from kb_distillery.services.ops import build_ops_snapshot, email_preview
from .shell import inject_nav

OPS_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops.html")


def handles(path):
    return path in ("/ops", "/ops.html", "/api/ops", "/ops/email-preview")


def handle(handler, path, query):
    """Serve one Ops route through the handler's _respond; returns True when the path was ours."""
    if path in ("/ops", "/ops.html"):
        with open(OPS_HTML, encoding="utf-8") as f:
            handler._respond(200, inject_nav(f.read(), "ops").encode("utf-8"), "text/html; charset=utf-8")
        return True
    if path == "/api/ops":
        try:
            data = build_ops_snapshot(refresh=(query.get("refresh") or [""])[0] == "1")
        except Exception as e:  # noqa: BLE001 — the tab shows the error instead of a blank page
            handler._respond(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode("utf-8"), "application/json")
            return True
        handler._respond(200, json.dumps(data, default=str).encode("utf-8"), "application/json")
        return True
    if path == "/ops/email-preview":
        html, _subject = email_preview()
        handler._respond(200, html.encode("utf-8"), "text/html; charset=utf-8")
        return True
    return False
