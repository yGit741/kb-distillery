"""Route inbox files to their format folder under raw/ and record membership. Zero LLM.

raw/ is split by FORMAT (how the bytes were produced), never by course or person: membership
is the corpus.tsv `collection` column, and a course/series hub lists its members in its
`## Contents` table. Only papers get a wiki stub at catalog time; emails, chats, handwriting and
slides stay corpus rows until something is actually digested from them.
"""
import os
import re
import shutil
import subprocess
import sys

from . import blog
from .paths import ROOT, person_from_raw, set_collection, _page_type
from .verify import existing_digest_for_raw
from kb.core.schema import (ASSET_NAME, RAW_CHATS, RAW_EMAILS, RAW_VIDEOS, VIDEO_ITEM, RAW_HANDWRITTEN, RAW_IMAGES,  # noqa: E402
                    RAW_PRESENTATIONS, RAW_PRINTED, RAW_WEB, CONTENTS_COLLECTIONS, make_slug, strip_prefix)

PAPER_NAME = re.compile(r"^(1[89]|20)\d{2}-[a-z0-9]+(-[a-z0-9]+)*\.pdf$")
TEXT_LAYER_CHARS = 200       # avg chars/page over the first pages; below this it's handwriting

SLIDE_EXTS = {".ppt", ".pptx", ".key"}
WEB_EXTS = {".html", ".htm", ".md"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

MAIL_DIR_PREFIX = "mail-"
VIDEO_DIR_PREFIX = "video-"     # scrap-youtube bundles
_ASSET_NAME = re.compile(ASSET_NAME, re.I)
_LINT_DEFERRED = False      # drain-inbox lints once at the end instead of after every file
CHAT_SIGNATURE = re.compile(r"\*\*You\*\*|\*\*Gemini\*\*|gemini\.google\.com", re.I)
WEB_CLIP_TAG = re.compile(r"^tags:.*\bsource/(wordpress|web-clip)\b", re.M)   # a scrap-wordpress / clipper clip
FORMATS = (RAW_PRINTED, RAW_HANDWRITTEN, RAW_PRESENTATIONS, RAW_CHATS, RAW_EMAILS, RAW_WEB,
           RAW_IMAGES, RAW_VIDEOS)


def _looks_like_chat(full_path):
    """Content-sniff a .md inbox file for the You/Gemini turn-marker pattern."""
    try:
        with open(full_path, encoding="utf-8", errors="ignore") as f:
            head = f.read(2000)
    except OSError:
        return False
    return bool(CHAT_SIGNATURE.search(head))


def _looks_like_web_clip(full_path):
    """A .md whose frontmatter tags say it is a web clip — its body may quote anything (a post that
    bolds the word You is not a Gemini export)."""
    try:
        with open(full_path, encoding="utf-8", errors="ignore") as f:
            head = f.read(2000)
    except OSError:
        return False
    return head.startswith("---") and bool(WEB_CLIP_TAG.search(head.split("\n---", 1)[0]))


def _looks_like_blog(full_path):
    """A .md whose frontmatter carries a known blog tag (e.g. source/blog-not-exact)."""
    try:
        with open(full_path, encoding="utf-8", errors="ignore") as f:
            head = f.read(2000)
    except OSError:
        return False
    fm, _, _ = blog.split(head if head.count("\n---") else head + "\n---\n")
    return blog.blog_of(fm) is not None


def has_text_layer(full_path, pages=5):
    """Typed PDFs carry text; reMarkable/scan exports are ink only. Unknown → typed."""
    try:
        import fitz  # pymupdf
    except ImportError:
        return True
    try:
        doc = fitz.open(full_path)
    except Exception:
        return True
    n = min(doc.page_count, pages) or 1
    chars = sum(len(doc[i].get_text()) for i in range(min(doc.page_count, pages)))
    doc.close()
    return chars / n >= TEXT_LAYER_CHARS


def detect_format(inbox_rel):
    """The raw/ format folder an inbox file or directory belongs in."""
    full = os.path.join(ROOT, inbox_rel)
    name = os.path.basename(inbox_rel.rstrip("/"))
    if os.path.isdir(full):
        if name.startswith(MAIL_DIR_PREFIX):
            return RAW_EMAILS
        if name.startswith(VIDEO_DIR_PREFIX) and os.path.isfile(os.path.join(full, VIDEO_ITEM)):
            return RAW_VIDEOS
        raise ValueError(f"{inbox_rel}/ is a folder — only mail-<thread>/ and video-<name>/ folders are cataloged whole")
    ext = os.path.splitext(name.lower())[1]
    if ext == ".pdf":
        return RAW_PRINTED if has_text_layer(full) else RAW_HANDWRITTEN
    if ext in SLIDE_EXTS:
        return RAW_PRESENTATIONS
    if ext == ".md" and _looks_like_blog(full):
        return RAW_PRINTED                              # a blog post is a typed document
    if ext == ".md" and _looks_like_web_clip(full):
        return RAW_WEB
    if ext == ".md" and _looks_like_chat(full):
        return RAW_CHATS
    if ext in WEB_EXTS:
        return RAW_WEB
    if ext in IMAGE_EXTS:
        return RAW_IMAGES
    raise ValueError(f"no format for {name!r} — pass --format ({', '.join(FORMATS)})")


def asset_clip(inbox_rel):
    """`<clip stem>-NN.<img>` next to `<clip stem>.md` (still in the inbox, or already in
    raw/web-clips/) is a figure of that clip — it goes to raw/images/ as its `asset:`, never
    as a hub member. Returns the clip stem, or None for a standalone image."""
    m = _ASSET_NAME.match(os.path.basename(inbox_rel))
    if not m:
        return None
    stem = m.group("clip")
    for d in ("raw/inbox", f"raw/{RAW_WEB}"):
        if os.path.isfile(os.path.join(ROOT, d, f"{stem}.md")):
            return stem
    return None


def _suggest_paper_name(filename, year=None):
    """A `<year>-<title>.pdf` name. The year is `year`, else read from the name; with neither there is
    no honest name: refuse instead of inventing `2000-…` (pass --year)."""
    if PAPER_NAME.match(filename) and not year:
        return filename
    base = re.sub(r"[^\w.\-]+", "-", os.path.splitext(filename)[0]).strip("-").lower()
    base = re.sub(r"^arxiv-", "", base)
    year_m = re.search(r"(1[89]\d{2}|20\d{2})", base)
    year = str(year) if year else (year_m.group(1) if year_m else "")
    if not year:
        raise ValueError(f"cannot tell the year of {filename!r} — pass --year YYYY (left in inbox)")
    title = re.sub(r"^\d{4}-?", "", base)
    title = re.sub(r"^[\d.\-v]+-?", "", title) or "untitled"
    return f"{year}-{title}.pdf"


ARXIV_SCRAPE = re.compile(r"^arxiv-(.+)\.pdf$", re.I)


def _arxiv_id_from_scrape(filename):
    """Invert scrap's naming: arxiv-2105-10386.pdf → 2105.10386, arxiv-math-9811157.pdf → math/9811157."""
    m = ARXIV_SCRAPE.match(filename)
    if not m:
        return None
    body = m.group(1)
    new = re.fullmatch(r"(\d{4})-(\d{4,5})", body)
    if new:
        return f"{new.group(1)}.{new.group(2)}"
    old = re.fullmatch(r"([a-z][a-z.-]*)_(\d{7})", body, re.I)
    if old:
        return f"{old.group(1)}/{old.group(2)}"
    return None


def _arxiv_lookup(filename):
    aid = _arxiv_id_from_scrape(filename)
    if not aid:
        return None
    from . import arxiv_meta
    try:
        return arxiv_meta.fetch([aid], strict=True).get(aid)
    except arxiv_meta.ArxivUnavailable as e:
        # never file an arXiv scrape as `2000-untitled.pdf`: that name then blocks every later
        # scrape ("destination exists") and hides the paper. Refuse; the file stays in the inbox.
        raise ValueError(f"arXiv metadata for {aid} unavailable ({e}) — left in inbox; "
                         "run `drain-inbox` again later")


def _ascii_slug(text, fallback="untitled"):
    text = re.sub(r"[^\w\s-]", "", text or "", flags=re.ASCII)
    text = re.sub(r"[\s_-]+", "-", text).strip("-").lower()
    return text or fallback


def _short(collection):
    """A hub's filename prefix: its `short:` frontmatter, else its slug without the type prefix."""
    path = os.path.join(ROOT, "wiki", f"{collection}.md")
    if os.path.isfile(path):
        from kb.lint.lint import parse_frontmatter
        short = (parse_frontmatter(open(path, encoding="utf-8").read()) or {}).get("short")
        if short:
            return str(short)
    return strip_prefix(collection)


def member_name(filename, collection=""):
    """`Lecture 3 - DP.pdf` in course-runi-rl (short: rl) → `rl-lecture-3-dp.pdf`: flat folders
    need names that stay unique across every course, so the collection's short name leads."""
    stem, ext = os.path.splitext(filename)
    stem = _ascii_slug(stem.replace(".", "-"))
    short = _short(collection) if collection else ""
    if short and not stem.startswith(f"{short}-"):
        stem = f"{short}-{stem}"
    return f"{stem}{ext.lower()}"


def _catalog_stub(slug, raw_rel, title=None, year=None, url="", authors=None):
    stem = strip_prefix(slug)
    title = title or re.sub(r"^(1[89]|20)\d{2}-", "", stem).replace("-", " ").title() or stem
    authors_yaml = "[" + ", ".join(re.sub(r"[,#\[\]]", "", a).strip() for a in (authors or [])) + "]"
    year = year or (stem[:4] if stem[:4].isdigit() else "")
    person = person_from_raw(raw_rel)
    recommended = f"[{person}]" if person else "[]"
    person_line = f"- Person: [[{person}]]\n" if person else ""
    return f"""---
type: paper
layer: source
authors: {authors_yaml}
year: {year}
area: []
status: to-read
depth: listed
raw: {raw_rel}
citekey:
url: {url}
recommended_by: {recommended}
discussed_with: []
---

# {title}

**Problem:**

**Main result:**

## Setup & assumptions

## Proof idea (sketch only)

## Key equations

## Takeaways for my thesis
-

## Links out
- Concepts: [[]]
{person_line}"""


def _move(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.abspath(src) == os.path.abspath(dest):
        return False
    if os.path.exists(dest):
        raise ValueError(f"destination exists: {os.path.relpath(dest, ROOT)}")
    shutil.move(src, dest)
    return True


def _check_inbox(inbox_rel):
    inbox_rel = inbox_rel.replace(os.sep, "/").lstrip("./").rstrip("/")
    if not inbox_rel.startswith("raw/inbox/"):
        raise ValueError(f"expected raw/inbox/ path, got {inbox_rel}")
    if not os.path.exists(os.path.join(ROOT, inbox_rel)):
        raise ValueError(f"not found: {inbox_rel}")
    return inbox_rel


def _join(dest_rel, collection, title):
    """Record membership: corpus.tsv `collection`, plus a Contents row on a course/series hub."""
    if not collection:
        return
    if _page_type(collection) in CONTENTS_COLLECTIONS:
        from . import course
        course.add_member(collection, dest_rel, title)
        print(f"listed on [[{collection}]] Contents")
    else:
        set_collection(dest_rel, [collection])
    print(f"collection → {collection}")


def catalog_paper(inbox_rel, collection="", slug=None, title=None, year=None, url=""):
    """A paper PDF → raw/printed-docs/<year>-<title>.pdf + a `paper-` catalog stub."""
    inbox_rel = _check_inbox(inbox_rel)
    filename = os.path.basename(inbox_rel)
    authors = None
    meta = None if slug else _arxiv_lookup(filename)
    if not url and not meta:
        from . import scrap
        url = scrap.source_url(os.path.join(ROOT, inbox_rel))     # recorded by `scrap` for non-arXiv PDFs
    if meta:
        title = title or meta["title"]
        year = year or meta["year"]
        url = url or meta["url"]
        authors = meta["authors"]
        slug = f"{meta['year']}-{_ascii_slug(meta['title'])[:80].strip('-')}"
        print(f"arxiv:{meta['id']} → {meta['title']} ({meta['year']}; {len(authors)} authors)")
    if slug:
        slug = strip_prefix(slug)
        filename = f"{slug}.pdf" if not slug.lower().endswith(".pdf") else slug
        if not PAPER_NAME.match(filename):
            filename = _suggest_paper_name(filename, year)
    elif title and not PAPER_NAME.match(filename):
        # not an arXiv scrape: --title names the paper (year from --year or the inbox name)
        filename = _suggest_paper_name(filename, year)
        year_part = str(year) if year else filename[:4]
        filename = f"{year_part}-{_ascii_slug(title)[:80].strip('-')}.pdf"
    else:
        filename = _suggest_paper_name(filename, year)
    stem = os.path.splitext(filename)[0]
    if year is None:
        year = stem[:4] if stem[:4].isdigit() else ""

    dest_rel = f"raw/{RAW_PRINTED}/{filename}"
    moved = _move(os.path.join(ROOT, inbox_rel), os.path.join(ROOT, dest_rel))
    print(f"{'moved' if moved else 'already at'} → {dest_rel}")
    _join(dest_rel, collection, title or stem)

    wiki_slug = make_slug("paper", stem)
    wiki_rel = f"wiki/{wiki_slug}.md"
    wiki_path = os.path.join(ROOT, wiki_rel)
    if not os.path.isfile(wiki_path):
        with open(wiki_path, "w", encoding="utf-8") as f:
            f.write(_catalog_stub(wiki_slug, dest_rel, title=title, year=year, url=url,
                                  authors=authors))
        print(f"created {wiki_rel} (depth: listed)")
    else:
        print(f"wiki exists: {wiki_rel}")
    _run_lint()
    return dest_rel, wiki_slug


def catalog_email(inbox_rel, collection="", **_kwargs):
    """raw/inbox/mail-<dir>/ → raw/emails/<dir>/. A corpus row only — a `mail-` page
    is written if the thread is ever worth digesting."""
    inbox_rel = _check_inbox(inbox_rel)
    dir_name = os.path.basename(inbox_rel)[len(MAIL_DIR_PREFIX):]
    dest_rel = f"raw/{RAW_EMAILS}/{dir_name}"
    moved = _move(os.path.join(ROOT, inbox_rel), os.path.join(ROOT, dest_rel))
    print(f"{'moved' if moved else 'already at'} → {dest_rel}/")
    _join(f"{dest_rel}/thread.md", collection, dir_name)
    _run_lint()
    return dest_rel, None


def _bundle_json(folder, name):
    import json
    try:
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def catalog_video(inbox_rel, collection="", title=None, **_kwargs):
    """raw/inbox/video-<dir>/ (scrap-youtube) → raw/videos/<dir>/. A corpus row only — the `video-`
    page is written by easy-digest, or a course row points at the bundle."""
    inbox_rel = _check_inbox(inbox_rel)
    dir_name = os.path.basename(inbox_rel)[len(VIDEO_DIR_PREFIX):]
    dest_rel = f"raw/{RAW_VIDEOS}/{dir_name}"
    dest, src = os.path.join(ROOT, dest_rel), os.path.join(ROOT, inbox_rel)
    old, new = _bundle_json(dest, "info.json"), _bundle_json(src, "info.json")
    aside = None
    if os.path.isdir(dest) and old.get("id") and old.get("id") == new.get("id"):
        # scrap-youtube --force: the same video's refreshed bundle. The old one goes to _quarantine/ (kept,
        # gitignored) rather than being deleted, so paid reads in an older bundle are never lost.
        if _bundle_json(dest, "video.json").get("anchors") and not _bundle_json(src, "video.json").get("anchors"):
            raise ValueError(f"{inbox_rel} has no anchors (no video downloaded?) — it would replace "
                             f"{dest_rel} which has them; re-scrap it first")
        from datetime import datetime
        aside = os.path.join(ROOT, "_quarantine", f"videos-{dir_name}-{datetime.now():%Y%m%d-%H%M%S}")
        os.makedirs(os.path.dirname(aside), exist_ok=True)
        shutil.move(dest, aside)
        print(f"refreshing {dest_rel}/ (same video) — the previous bundle is in {os.path.relpath(aside, ROOT)}/")
    try:
        moved = _move(src, dest)
    except (OSError, ValueError):
        if aside:
            shutil.move(aside, dest)                   # put the previous bundle back
        raise
    print(f"{'moved' if moved else 'already at'} → {dest_rel}/")
    title = title or _bundle_json(dest, "video.json").get("title")
    _join(f"{dest_rel}/{VIDEO_ITEM}", collection, title or dir_name)
    _run_lint()
    return dest_rel, None


def catalog_chat(inbox_rel, collection="", **_kwargs):
    """A chat-export .md → raw/llm-chats/, repointing an existing digest that cited the inbox path."""
    inbox_rel = _check_inbox(inbox_rel)
    stem = os.path.splitext(os.path.basename(inbox_rel))[0]
    dest_rel = f"raw/{RAW_CHATS}/{_ascii_slug(stem, fallback=f'chat-{_short_hash(inbox_rel)}')}.md"
    moved = _move(os.path.join(ROOT, inbox_rel), os.path.join(ROOT, dest_rel))
    print(f"{'moved' if moved else 'already at'} → {dest_rel}")
    _join(dest_rel, collection, stem)

    wiki_slug = None
    existing_wiki = existing_digest_for_raw(inbox_rel)
    if existing_wiki:
        wiki_path = os.path.join(ROOT, existing_wiki)
        text = open(wiki_path, encoding="utf-8").read()
        if f"raw: {inbox_rel}" in text:
            with open(wiki_path, "w", encoding="utf-8") as f:
                f.write(text.replace(f"raw: {inbox_rel}", f"raw: {dest_rel}", 1))
            print(f"rewrote raw: in {existing_wiki} → {dest_rel}")
        wiki_slug = os.path.splitext(os.path.basename(existing_wiki))[0]
    _run_lint()
    return dest_rel, wiki_slug


def catalog_file(inbox_rel, fmt, collection="", title=None, **_kwargs):
    """Any other file → raw/<fmt>/<collection-stem>-<kebab-name>.<ext>. A corpus row only."""
    inbox_rel = _check_inbox(inbox_rel)
    filename = os.path.basename(inbox_rel)
    dest_rel = f"raw/{fmt}/{member_name(filename, collection)}"
    moved = _move(os.path.join(ROOT, inbox_rel), os.path.join(ROOT, dest_rel))
    print(f"{'moved' if moved else 'already at'} → {dest_rel}")
    if not title and dest_rel.endswith(".md"):
        title = _clip_title(dest_rel)                  # a web clip's own title, not its file stem
    _join(dest_rel, collection, title or os.path.splitext(filename)[0])
    _run_lint()
    return dest_rel, None


def _clip_title(rel):
    """`title:` from a raw .md clip's frontmatter (scrap-wordpress, Web Clipper), or ''."""
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore") as f:
            head = f.read(2000)
    except OSError:
        return ""
    if not head.startswith("---"):
        return ""
    import json
    for line in head.split("\n---", 1)[0].split("\n"):
        if line.startswith("title:"):
            val = line[6:].strip()
            if val.startswith('"'):
                try:
                    return json.loads(val)
                except ValueError:
                    return val.strip('"')
            return val.strip("'")
    return ""


def _short_hash(rel):
    import hashlib
    h = hashlib.sha1()
    with open(os.path.join(ROOT, rel), "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:8]


def catalog_blog(inbox_rel, collection="", **_kwargs):
    """A tagged blog post → raw/printed-docs/<blog>-<slug>.md + a `blog-post` page (blog.render)."""
    inbox_rel = _check_inbox(inbox_rel)
    src = os.path.join(ROOT, inbox_rel)
    with open(src, encoding="utf-8") as f:
        fm, _title, _ = blog.split(f.read())
    tag, _info = blog.blog_of(fm)
    prefix = tag.split("/", 1)[1]  # source/blog-not-exact → blog-not-exact
    stem = os.path.splitext(os.path.basename(inbox_rel))[0]
    dest_rel = f"raw/{RAW_PRINTED}/{prefix}-{_ascii_slug(stem, fallback=_short_hash(inbox_rel))}.md"
    moved = _move(src, os.path.join(ROOT, dest_rel))
    print(f"{'moved' if moved else 'already at'} → {dest_rel}")
    _join(dest_rel, collection, _title or stem)
    wiki_slug = blog.wiki_slug(dest_rel)
    wiki_rel = f"wiki/{wiki_slug}.md"
    if not os.path.isfile(os.path.join(ROOT, wiki_rel)):
        with open(os.path.join(ROOT, wiki_rel), "w", encoding="utf-8") as f:
            f.write(blog.render(dest_rel))
        print(f"created {wiki_rel} (depth: listed)")
    _run_lint()
    return dest_rel, wiki_slug


CATALOG_LOG_DIR = os.path.join(ROOT, "meta", ".catalog")


def log_event(kind, **fields):
    """Append to meta/.catalog/<kind>.jsonl — `events` (cataloged) or `failures` (refused, with the
    reason). The dashboard's Ingestion status reads these; nothing else depends on them."""
    import json
    from datetime import datetime, timezone
    os.makedirs(CATALOG_LOG_DIR, exist_ok=True)
    fields["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(os.path.join(CATALOG_LOG_DIR, f"{kind}.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(fields, ensure_ascii=False) + "\n")


def catalog(inbox_rel, collection="", fmt=None, title=None, year=None):
    """Detect the format (or take --format) and route. A typed PDF is a paper unless it joins a
    course/series, where it is a member row (a course book, typed notes) instead.
    Every outcome is logged: a refusal keeps its reason so the inbox can show why a file is stuck."""
    rel = inbox_rel.replace(os.sep, "/").lstrip("./").rstrip("/")
    try:
        fmt = fmt or detect_format(rel)
        print(f"format → {fmt}")
        if fmt == RAW_EMAILS:
            dest, slug = catalog_email(rel, collection=collection)
        elif fmt == RAW_VIDEOS:
            dest, slug = catalog_video(rel, collection=collection, title=title)
        elif fmt == RAW_CHATS:
            dest, slug = catalog_chat(rel, collection=collection)
        elif fmt == RAW_PRINTED and rel.lower().endswith(".md") and _looks_like_blog(os.path.join(ROOT, rel)):
            dest, slug = catalog_blog(rel, collection=collection)
        elif fmt == RAW_IMAGES and asset_clip(rel):
            print(f"figure of {asset_clip(rel)}.md — not a member of {collection or 'anything'} on its own")
            dest, slug = catalog_file(rel, fmt)              # lint binds it as asset:<clip>
        elif (fmt == RAW_PRINTED and rel.lower().endswith(".pdf")
                and _page_type(collection) not in CONTENTS_COLLECTIONS):
            dest, slug = catalog_paper(rel, collection=collection, title=title, year=year)
        else:
            dest, slug = catalog_file(rel, fmt, collection=collection, title=title)
    except (ValueError, NotImplementedError, OSError) as e:
        log_event("failures", path=rel, reason=str(e), collection=collection, format=fmt or "")
        raise
    log_event("events", path=rel, dest=dest, slug=slug or "", collection=collection, format=fmt)
    return dest, slug


def drain_inbox(collection="", match=""):
    """Catalog every file/dir in raw/inbox/ — or, with `match`, only the entries whose name starts
    with it (a scrap-wordpress pull next to unrelated inbox files)."""
    inbox = os.path.join(ROOT, "raw", "inbox")
    if not os.path.isdir(inbox):
        print("inbox empty")
        return []
    global _LINT_DEFERRED
    results = []
    # clips before their figures, so a figure always finds its clip; one lint at the end
    names = sorted((fn for fn in os.listdir(inbox) if not fn.startswith(".") and fn.startswith(match)),
                   key=lambda fn: (not fn.endswith(".md"), fn))
    _LINT_DEFERRED = True
    try:
        for fn in names:
            rel = f"raw/inbox/{fn}"
            try:
                results.append(catalog(rel, collection=collection))
            except (ValueError, NotImplementedError, OSError) as e:      # logged; keep draining
                print(f"skip {rel}: {e}", file=sys.stderr)
    finally:
        _LINT_DEFERRED = False
    if results:
        _run_lint()
    return results


def _run_lint():
    if _LINT_DEFERRED:
        return
    subprocess.run(
        [sys.executable, "-m", "kb.lint.lint"],
        cwd=ROOT,
        check=False,
    )
