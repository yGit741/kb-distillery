"""Scrap a WordPress.com blog into raw/inbox/ — every post as a Markdown clip plus its images.

    python3 -m kb_distillery.ingest scrap-wordpress gilkalai.wordpress.com --prefix kalai-blog

One post → `raw/inbox/<prefix>-<YYYY-MM-DD>-<slug>.md`; its figures → `raw/inbox/<same stem>-NN.<ext>`,
linked from the clip as `../images/<file>` (the path they resolve to once catalog has moved the
clip to raw/web-clips/ and the images to raw/images/). The original image URL is kept as the
link title, so a figure can always be re-fetched or compared. A figure that cannot be
downloaded keeps its remote URL in the clip instead.

Math: WordPress.com renders `$latex …$` as `<img src="…/latex.php?latex=<tex>…">`. The TeX
source is in the URL, so every formula is restored losslessly as `$…$` (or `$$…$$` for
`\\displaystyle`). Embedded players (`<iframe>`) become a link line. Everything else goes
through src/kb_distillery/ingest/sources/web/htmlmd.py (standard library only).

Source: the public REST API (`public-api.wordpress.com/rest/v1.1/sites/<site>/posts`), 100 posts
per page, oldest first, so a `--since` date resumes an earlier pull. Dedup is by post URL against
the `url:` frontmatter of clips already in raw/web-clips/ or raw/inbox/ (`--force` re-pulls).
"""
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import htmlmd
from kb_distillery.ingest.paths import ROOT

API = "https://public-api.wordpress.com/rest/v1.1/sites/{site}/posts/"
FIELDS = "ID,date,modified,title,URL,slug,categories,tags,word_count,content"
PAGE = 100
PAUSE = 0.3                      # seconds between API pages
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
IMAGE_WORKERS = 8
UA = "thesis-kb/0.1 (+https://github.com/yGit741/yonatan-thesis-kb)"
SLUG_MAX = 60
INBOX = "raw/inbox"
WEB = "raw/web-clips"


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
def site_of(text):
    """`gilkalai.wordpress.com`, `https://gilkalai.wordpress.com/2020/…` → `gilkalai.wordpress.com`."""
    text = text.strip()
    if "://" in text:
        text = urllib.parse.urlparse(text).netloc
    return text.strip("/").lower()


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def iter_posts(site, since=None, limit=None, fetch=_get_json):
    """Yield post dicts oldest first. `since`: ISO date — only posts published on/after it."""
    handle = None
    seen = 0
    while True:
        q = {"number": PAGE, "order": "asc", "order_by": "date", "fields": FIELDS}
        if since:
            q["after"] = f"{since}T00:00:00"
        if handle:
            q["page_handle"] = handle
        data = fetch(API.format(site=site) + "?" + urllib.parse.urlencode(q))
        posts = data.get("posts") or []
        for p in posts:
            yield p
            seen += 1
            if limit and seen >= limit:
                return
        handle = (data.get("meta") or {}).get("next_page")
        if not handle or not posts:
            return
        time.sleep(PAUSE)


# --------------------------------------------------------------------------
# naming
# --------------------------------------------------------------------------
def kebab(text, n=SLUG_MAX):
    text = unicodedata.normalize("NFKD", html.unescape(text or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:n].rstrip("-")


def _words(slug):
    """A usable kebab slug only when it has real ASCII words: a Hebrew slug arrives percent-encoded
    (`%d7%a9…`) and would otherwise turn into hex soup, and a decoded one has no ASCII at all."""
    s = kebab(urllib.parse.unquote(slug or ""))
    return s if re.search(r"[a-z]{3}", s) else ""


def clip_stem(post, prefix):
    day = post["date"][:10]
    slug = _words(post.get("slug")) or _words(post.get("title")) or f"post-{post['ID']}"
    return f"{prefix}-{day}-{slug}"


# --------------------------------------------------------------------------
# conversion
# --------------------------------------------------------------------------
_IMG = re.compile(r"<img\b[^>]*>", re.I)
_ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')
_IFRAME = re.compile(r"<iframe\b[^>]*>.*?</iframe>|<iframe\b[^>]*/?>", re.I | re.S)
_YT = re.compile(r"youtube(?:-nocookie)?\.com/embed/([\w-]+)")


def _attrs(tag):
    return {k.lower(): html.unescape(v) for k, v in _ATTR.findall(tag)}


def tex_of(src):
    """The LaTeX source carried by a WordPress.com latex.php image URL."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(html.unescape(src)).query)
    return (q.get("latex") or [""])[0].strip()


DISPLAY = "\\displaystyle"


TOKEN = "\ue000{}\ue001"                        # private-use chars: survive the HTML parser untouched
_TOKEN = re.compile("\ue000(\\d+)\ue001")


def _wrapped_in_braces(tex):
    """True when the first `{` and the last `}` are a pair: `{a+b}` yes, `{\\cal D}_x U^{-1}` no
    (equal counts are not enough — the group closes early). Escaped `\\{` `\\}` don't count."""
    if not (tex.startswith("{") and tex.endswith("}")):
        return False
    depth = 0
    for i, ch in enumerate(re.sub(r"\\[{}]", "  ", tex)):
        depth += (ch == "{") - (ch == "}")
        if depth == 0:
            return i == len(tex) - 1
    return False


def _math_md(tex):
    """`$…$` / a display block for one latex.php formula."""
    if tex.startswith(DISPLAY):
        body = tex[len(DISPLAY):].strip()
        return f"\n\n$$\n{body}\n$$\n\n" if body else ""
    if _wrapped_in_braces(tex):
        tex = tex[1:-1].strip()
    return f"${tex}$" if tex else ""


def restore_math(md, maths):
    """Put the formulas back after Markdown conversion (they were protected as tokens)."""
    md = _TOKEN.sub(lambda m: maths[int(m.group(1))], md)
    md = re.sub(r"[ \t]*\n\n\$\$\n", "\n\n$$\n", md)
    return re.sub(r"\n{3,}", "\n\n", md)


def _image_ext(url):
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    return ext if ext in IMAGE_EXTS else None


def prepare(content, stem):
    """Rewrite the post HTML before Markdown conversion. Returns (html, images, maths, stats):
    images = [(file name, full-size URL)] in order of appearance (not yet downloaded);
    maths = the Markdown of each formula, referenced from the HTML by TOKEN placeholders."""
    images = []
    maths = []
    stats = {"formulas": 0, "images": 0, "embeds": 0}

    def img(m):
        a = _attrs(m.group(0))
        src = a.get("src", "")
        if src.startswith("//"):
            src = "https:" + src
        if "latex.php" in src:
            stats["formulas"] += 1
            maths.append(_math_md(tex_of(src)))
            return TOKEN.format(len(maths) - 1)
        if not src:
            return ""
        full = src.split("?")[0]                       # ?w=640&h=480 is a resized variant
        ext = _image_ext(full)
        stats["images"] += 1
        alt = a.get("alt", "").replace("]", "").replace("\n", " ").strip()
        if not ext:                                    # svg, data:, odd hosts: keep remote
            return f'<img src="{html.escape(src)}" alt="{html.escape(alt)}">'
        n = len(images) + 1
        name = f"{stem}-{n:02d}{ext}"
        images.append((name, full))
        return f'<img src="../images/{name}" alt="{html.escape(alt)}" title="{html.escape(full)}">'

    def frame(m):
        a = _attrs(m.group(0))
        src = a.get("src", "")
        stats["embeds"] += 1
        yt = _YT.search(src)
        link = f"https://www.youtube.com/watch?v={yt.group(1)}" if yt else src
        return f'<p>▶ Embedded video: <a href="{html.escape(link)}">{html.escape(link)}</a></p>' if link else ""

    content = _IFRAME.sub(frame, content)
    content = _IMG.sub(img, content)
    # a linked figure `<a href=full><img …></a>` → just the figure
    content = re.sub(r'<a\b[^>]*href="([^"]+)"[^>]*>\s*(<img src="\.\./images/[^"]+" alt="[^"]*" title="([^"]+)">)\s*</a>',
                     lambda m: m.group(2) if m.group(1).split("?")[0] == m.group(3) else m.group(0), content)
    return content, images, maths, stats


def frontmatter(post, site, stats, fetched=None):
    q = lambda s: json.dumps(html.unescape(s or ""), ensure_ascii=False)
    cats = ", ".join(q(c) for c in sorted((post.get("categories") or {}).keys()))
    tags = ", ".join(q(c) for c in sorted((post.get("tags") or {}).keys()))
    lines = ["---", f"title: {q(post.get('title'))}", f"blog: {q(site)}", f"url: {post['URL']}",
             f"date: {post['date'][:10]}", f"modified: {(post.get('modified') or post['date'])[:10]}",
             f"categories: [{cats}]", f"post_tags: [{tags}]", f"words: {post.get('word_count', 0)}",
             f"formulas: {stats['formulas']}", f"images: {stats['images']}", f"embeds: {stats['embeds']}",
             f"source: wordpress.com REST API v1.1", f"fetched: {fetched or date.today().isoformat()}",
             f"tags: [source/wordpress, blog/{kebab(site)}]", "---", ""]
    return "\n".join(lines)


def to_clip(post, site, prefix, fetched=None):
    """(stem, markdown text, images to download, stats) for one API post."""
    stem = clip_stem(post, prefix)
    body_html, images, maths, stats = prepare(post.get("content") or "", stem)
    body = restore_math(htmlmd.to_markdown(body_html), maths)
    title = html.unescape(post.get("title") or stem)
    text = (frontmatter(post, site, stats, fetched) + f"# {title}\n\n"
            f"> Original: {post['URL']} · {post['date'][:10]}\n\n" + body)
    return stem, text, images, stats


# --------------------------------------------------------------------------
# download
# --------------------------------------------------------------------------
def download(url, dest):
    """Fetch url to dest. Returns True on success; a missing/forbidden figure is not fatal."""
    if os.path.exists(dest):
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if not data:
            return False
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return False


def _restore_remote(text, name, url):
    """A figure that could not be fetched keeps its original URL in the clip."""
    return text.replace(f'](../images/{name} "{url}")', f"]({url})")


# --------------------------------------------------------------------------
# dedup
# --------------------------------------------------------------------------
_URL_LINE = re.compile(r"^url:\s*(\S+)\s*$", re.M)


def known_urls(root=ROOT):
    """Post URLs of clips already in raw/web-clips/ or raw/inbox/ (frontmatter `url:`)."""
    urls = set()
    for sub in (WEB, INBOX):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".md"):
                continue
            try:
                with open(os.path.join(d, fn), encoding="utf-8", errors="ignore") as f:
                    head = f.read(1500)
            except OSError:
                continue
            m = _URL_LINE.search(head.split("\n---", 1)[0] if head.startswith("---") else "")
            if m:
                urls.add(m.group(1).rstrip("/"))
    return urls


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------
def scrap_wordpress(site, prefix=None, since=None, limit=None, images=True, force=False,
                    root=ROOT, fetch=_get_json, fetch_image=download):
    """Pull a blog into raw/inbox/. Returns the inbox-relative paths written (clips, then images)."""
    site = site_of(site)
    prefix = prefix or kebab(site.split(".")[0])
    inbox = os.path.join(root, "raw", "inbox")
    os.makedirs(inbox, exist_ok=True)
    skip = set() if force else known_urls(root)
    today = date.today().isoformat()
    written, pending, skipped = [], [], 0
    for post in iter_posts(site, since=since, limit=limit, fetch=fetch):
        if post["URL"].rstrip("/") in skip:
            skipped += 1
            continue
        stem, text, imgs, stats = to_clip(post, site, prefix, fetched=today)
        md_rel = f"{INBOX}/{stem}.md"
        if images:
            pending.append((md_rel, text, imgs))
        else:
            for name, url in imgs:
                text = _restore_remote(text, name, url)
            pending.append((md_rel, text, []))
        print(f"{stem}: {stats['formulas']} formulas · {stats['images']} images · {stats['embeds']} embeds")

    failed = 0
    jobs = [(name, url, os.path.join(inbox, name)) for _rel, _t, imgs in pending for name, url in imgs]
    ok = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as ex:
            for (name, url, dest), good in zip(jobs, ex.map(lambda j: fetch_image(j[1], j[2]), jobs)):
                ok[name] = good
    for md_rel, text, imgs in pending:
        for name, url in imgs:
            if ok.get(name):
                written.append(f"{INBOX}/{name}")
            else:
                failed += 1
                text = _restore_remote(text, name, url)
        with open(os.path.join(root, md_rel), "w", encoding="utf-8") as f:
            f.write(text)
        written.append(md_rel)
    clips = sum(1 for p in written if p.endswith(".md"))
    print(f"scrap-wordpress {site}: {clips} posts · {len(written) - clips} images"
          f"{f' · {failed} figures kept remote (not downloadable)' if failed else ''}"
          f"{f' · {skipped} already in the vault' if skipped else ''} → raw/inbox/")
    if clips:
        print("next: python3 -m kb_distillery.ingest drain-inbox --collection <series-hub>")
    return written
