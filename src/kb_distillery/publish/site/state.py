"""The share status chip and log tail the app shows: what the configured publisher last published.

Plain data in, plain data out: no HTML, no dashboard import. `kb_distillery.server.routers.share` serves it."""
import datetime as _dt

SHARE_LOG_LINES = 200


def _age(at, now):
    try:
        secs = int((now - _dt.datetime.fromisoformat(at)).total_seconds())
    except (TypeError, ValueError):
        return ""
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"


def share_state(publisher=None):
    """{status, chip} of the configured publisher's last publish. With no publisher the chip says so (the app and
    the API must render without one); a publisher that cannot be read counts as nothing published."""
    from kb_distillery import publish
    pub = publisher or publish.current()
    try:
        status = pub.status()
    except Exception:  # noqa: BLE001 — a publisher hiccup must not take the screen down
        status = None
    chip = share_chip(status)
    if chip is None and isinstance(pub, publish.NullPublisher):
        chip = {"label": "no publisher", "cls": "is-skipped", "title": f"share: {pub.reason}", "href": ""}
    return {"status": status, "chip": chip}


def share_chip(status, now=None):
    """Chip for the share deploy status file: {label, cls, title, href} or None when nothing was deployed yet.

    States: deployed (green, "kb <version> · <age>"), deploying, skipped-* (muted), failed and
    refused-no-access (red, title = error, links to /share-log).
    """
    if not status or not status.get("state"):
        return None
    now = now or _dt.datetime.now(_dt.timezone.utc)
    state = status["state"]
    version = f"kb-{status['kb_version']}" if status.get("kb_version") else "kb"
    age = _age(status.get("at"), now)
    url = status.get("url") or ""
    if state == "deployed":
        return {"label": f"{version} · {age}" if age else version, "cls": "is-deployed",
                "title": f"share: deployed {status.get('sha', '')[:9]} {status.get('at', '')}", "href": url or "/share-log"}
    if state == "deploying":
        return {"label": f"deploying {version}", "cls": "is-deploying",
                "title": f"share: deploy in progress since {status.get('at', '')}", "href": "/share-log"}
    if state.startswith("skipped-"):
        return {"label": f"{state} · {age}" if age else state, "cls": "is-skipped",
                "title": f"share: {state} — {status.get('error') or 'live site already matches'}", "href": "/share-log"}
    return {"label": f"deploy {state}" if state != "failed" else "deploy failed", "cls": "is-failed",
            "title": f"share: {status.get('error') or state}", "href": "/share-log"}


def share_log_tail(n=SHARE_LOG_LINES):
    try:
        from kb_distillery import publish
        return publish.current().log_tail(n)
    except Exception:  # noqa: BLE001
        return "no share log yet\n"
