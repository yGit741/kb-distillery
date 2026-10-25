"""One raw file as a small card for the Home pipeline strip (0 LLM).

`raw_card(full, rel)` reads the file once and returns {kind, format, ext, name, facts, title, site, url,
excerpt, turns, header, has_thumb}. The local API serves it at `/api/raw/{path}/card` (the thumbnail is
fetched separately from `/thumb`); the share build bakes it per source page with `thumb` as a small data
URI and, for the public profile, `public_card` applies the privacy column (chats and emails: facts only;
no file name anywhere).
"""
import base64
import os
import re
import subprocess

PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TEXT_EXT = {".md", ".txt", ".html", ".htm", ".eml", ".json"}
EXCERPT_CHARS = 420
TURN_CHARS = 220
MAX_TURNS = 3
YOUTUBE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{6,})")
_FM = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
_TURN = re.compile(r"^\*\*(You|User|Me|Gemini|ChatGPT|Claude|Assistant|Copilot)\*\*\s*$", re.M | re.I)
_TAG = re.compile(r"<[^>]+>")


def kind_of(fmt, ext, url=""):
    if fmt == "llm-chats":
        return "chat"
    if fmt == "emails":
        return "email"
    if ext in IMAGE_EXT:
        return "image"
    if ext in PDF_EXT:
        return {"handwritten": "handwritten", "presentations": "slides"}.get(fmt, "pdf")
    if fmt == "presentations":
        return "slides"
    if fmt == "web-clips":
        return "youtube" if YOUTUBE.search(url or "") else "web"
    return "other"


def frontmatter(text):
    """Flat `key: value` pairs of a YAML front matter (quotes stripped); ({}, text) without one."""
    m = _FM.match(text)
    if not m:
        return {}, text
    out = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep and k and not k.startswith((" ", "-")):
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out, text[m.end():]


def plain(md, limit=EXCERPT_CHARS):
    """Markdown/HTML to a short plain excerpt: no headings markers, links, images, emphasis or tags."""
    s = _TAG.sub(" ", md)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"[*_`>]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "…"


def chat_turns(body):
    """[{role, text}] of the first MAX_TURNS turns of a clipped chat (`**You**` / `**Gemini**` markers)."""
    marks = list(_TURN.finditer(body))
    turns = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        who = m.group(1)
        role = "user" if who.lower() in ("you", "user", "me") else "model"
        text = plain(body[m.end():end].replace("\n---\n", "\n"), TURN_CHARS)
        if text:
            turns.append({"role": role, "text": text})
    return turns, len(marks)


def model_of(url, body):
    u = (url or "").lower()
    for host, name in (("gemini.google", "Gemini"), ("chatgpt.com", "ChatGPT"), ("chat.openai", "ChatGPT"), ("claude.ai", "Claude")):
        if host in u:
            return name
    m = _TURN.search(body)
    if m and m.group(1).lower() not in ("you", "user", "me", "assistant"):
        return m.group(1)
    return None


def pdf_pages(full):
    try:
        import fitz  # pymupdf
        with fitz.open(full) as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001
        return None


def added_date(root, rel):
    """Date the file was first committed, else its mtime date ('YYYY-MM-DD'), else None."""
    try:
        p = subprocess.run(["git", "log", "--diff-filter=A", "--follow", "--format=%as", "--", rel], cwd=root,
                           capture_output=True, text=True, timeout=10, check=False)
        dates = p.stdout.split()
        if dates:
            return dates[-1]
    except Exception:  # noqa: BLE001
        pass
    try:
        import datetime
        return datetime.date.fromtimestamp(os.path.getmtime(os.path.join(root, rel))).isoformat()
    except OSError:
        return None


def raw_card(full, rel, root=None, with_added=True):
    """The card for one existing raw file (`full` absolute, `rel` = raw/<format>/…)."""
    ext = os.path.splitext(rel)[1].lower()
    fmt = rel.split("/")[1] if rel.count("/") >= 2 else ""
    card = {"path": rel, "name": os.path.basename(rel), "format": fmt, "ext": ext.lstrip("."),
            "kind": "other", "facts": {"bytes": None, "pages": None, "added": None}, "title": None, "site": None,
            "url": None, "excerpt": None, "turns": [], "turn_count": None, "model": None, "header": None,
            "has_thumb": False, "thumb": None}
    try:
        card["facts"]["bytes"] = os.path.getsize(full)
    except OSError:
        return card
    if with_added and root:
        card["facts"]["added"] = added_date(root, rel)
    text, meta = "", {}
    if ext in TEXT_EXT:
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                text = f.read(200_000)
        except OSError:
            text = ""
        meta, text = frontmatter(text)
    url = next((meta[k] for k in ("source_url", "url", "source") if meta.get(k, "").startswith("http")), "")
    if ext in (".html", ".htm") and not url:
        m = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', text) or re.search(r'property="og:url"[^>]+content="([^"]+)"', text)
        url = m.group(1) if m else ""
    kind = kind_of(fmt, ext, url)
    card["kind"] = kind
    card["url"] = url or None
    if url:
        card["site"] = meta.get("blog") or re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/")[0]) or None
    if kind in ("pdf", "handwritten", "slides") and ext in PDF_EXT:
        card["facts"]["pages"] = pdf_pages(full)
        card["has_thumb"] = True
    elif kind == "image":
        card["has_thumb"] = True
    if ext in (".html", ".htm"):
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
        card["title"] = (m.group(1).strip() if m else None) or meta.get("title")
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
        card["excerpt"] = plain(body) or None
    elif ext in TEXT_EXT:
        card["title"] = meta.get("title") or None
        if kind == "chat":
            turns, n = chat_turns(text)
            card["turns"], card["turn_count"] = turns[:MAX_TURNS], n
            card["model"] = model_of(url, text)
        elif kind == "email":
            card["header"] = {"sender": meta.get("from") or meta.get("participants", "").strip("[]") or None, "date": meta.get("date") or meta.get("date-range"), "subject": meta.get("subject") or meta.get("title")}
            card["excerpt"] = plain(text) or None
        else:
            body = re.sub(r"\A\s*#\s[^\n]*\n", "", text)
            card["excerpt"] = plain(re.sub(r"^(Original|Source):.*$", "", body, flags=re.M)) or None
        if kind == "youtube":
            m = YOUTUBE.search(url)
            card["video_id"] = m.group(1) if m else None
    return card


def thumb_data_uri(full, kind, width=200, max_bytes=40_000):
    """A small JPEG data URI of page 1 (PDF) or the image itself, kept under `max_bytes`; None otherwise."""
    try:
        import fitz  # pymupdf
        with fitz.open(full) as doc:              # an image opens as a one-page document too
            page = doc[0]
            zoom = min(1.0, width / max(page.rect.width, 1)) if kind == "image" else width / max(page.rect.width, 1)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        for q in (70, 55, 40):
            data = pix.tobytes("jpeg", jpg_quality=q)
            if len(data) <= max_bytes:
                return "data:image/jpeg;base64," + base64.b64encode(data).decode()
    except Exception:  # noqa: BLE001
        return None
    return None


PRIVATE_KINDS = ("chat", "email")


def public_card(card):
    """The privacy column: no file name or path anywhere; chats and emails keep facts only."""
    out = dict(card, path=None, name=None)
    if card.get("kind") in PRIVATE_KINDS or card.get("kind") == "other":
        out.update(title=None, excerpt=None, turns=[], header=None, url=None, site=None)
    return out


def added_dates(root):
    """{raw/… path: first-commit date} for every tracked raw file, in one `git log` pass."""
    try:
        p = subprocess.run(["git", "log", "--diff-filter=A", "--name-only", "--format=@%as", "--", "raw"], cwd=root,
                           capture_output=True, text=True, timeout=60, check=False)
    except Exception:  # noqa: BLE001
        return {}
    out, date = {}, None
    for line in p.stdout.splitlines():
        if line.startswith("@"):
            date = line[1:]
        elif line.strip() and date:
            out[line.strip()] = date              # newest first: the last write is the oldest add
    return out


DEPTH_RANK = {"deep": 0, "full": 1, "easy": 2, "listed": 3}


def bake_cards(nodes, raw_of, raw_root, public=False, thumb_budget=6_000_000, width=200):
    """{slug: card} for the source nodes kept in a share build. Thumbnails (≤ ~40 KB JPEG each) go to the
    best-read sources first until `thumb_budget` bytes are spent; the rest show a format icon."""
    added = added_dates(raw_root)
    sources = [n for n in nodes if n.get("layer") == "source" and raw_of.get(n["id"])]
    sources.sort(key=lambda n: (DEPTH_RANK.get(n.get("depth") or "listed", 4), n["id"]))
    cards, spent = {}, 0
    for n in sources:
        rel = raw_of[n["id"]]
        full = os.path.join(raw_root, rel)
        if not rel.startswith("raw/") or ".." in rel.split("/") or rel.startswith("raw/inbox/") or not os.path.isfile(full):
            continue
        card = raw_card(full, rel, raw_root, with_added=False)
        card["facts"]["added"] = added.get(rel)
        if card["has_thumb"] and spent < thumb_budget:
            card["thumb"] = thumb_data_uri(full, card["kind"], width)
            spent += len(card["thumb"] or "")
        card["has_thumb"] = bool(card["thumb"])
        cards[n["id"]] = public_card(card) if public else card
    return cards
