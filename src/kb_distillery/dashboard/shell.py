"""Shared navigation shell for the legacy dashboard tabs (the share chip lives in publish.site_state)."""
import html

from kb_distillery.publish.site_state import share_chip, share_state  # noqa: F401 (re-exported for the legacy pages)

TABS = [
    ("start", "/start", "Start"),
    ("health", "/", "Health"),
    ("graph", "/app/graph", "Graph"),
    ("explore", "/explore", "Explore"),
    ("scopes", "/scopes", "Scopes"),
    ("chat", "/chat", "Chat"),
    ("pipeline", "/pipeline", "Pipeline"),
    ("lifecycle", "/lifecycle", "Lifecycle"),
    ("ops", "/ops", "Ops"),
]


def render_nav(active: str) -> str:
    links = []
    for tab_id, href, label in TABS:
        cls = ' class="active"' if tab_id == active else ""
        links.append(f'<a href="{href}"{cls}>{html.escape(label)}</a>')
    return (
        f'<nav class="app-nav" aria-label="Main">'
        f'<div class="app-nav-tabs">{"".join(links)}</div>'
        f'<div class="app-nav-right">'
        f'<a class="share-chip" id="share-chip" hidden></a>'
        f'<button type="button" class="theme-toggle" id="theme-toggle" '
        f'aria-label="Toggle light/dark theme" title="Toggle theme">'
        f'<span class="theme-icon theme-icon-sun" aria-hidden="true">☀</span>'
        f'<span class="theme-icon theme-icon-moon" aria-hidden="true">☾</span>'
        f"</button></div></nav>"
    )


def inject_nav(html_content: str, active: str) -> str:
    return html_content.replace("{{NAV}}", render_nav(active))
