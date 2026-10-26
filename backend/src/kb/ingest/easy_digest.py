"""Lightweight abstract extraction for easy-digest. Agent fills summary."""
import os
import re
import subprocess
import sys

from .extract import extract_text
from .paths import ROOT, sha1_file
from .verify import existing_digest_for_raw
from kb.core import wikiio
from kb.core.schema import unit_slug_for_raw, unit_type_for_raw

EASY_DIR = os.path.join(ROOT, "meta", ".ingest", "easy")


def _resolve_raw(arg):
    arg = arg.replace(os.sep, "/").lstrip("./")
    if arg.startswith("raw/"):
        return arg
    wiki = os.path.join(ROOT, "wiki", f"{arg}.md" if not arg.endswith(".md") else arg)
    if not os.path.isfile(wiki):
        raise ValueError(f"no wiki page or raw path: {arg}")
    text = open(wiki, encoding="utf-8").read()
    m = re.search(r"^raw:\s*(\S+)", text, re.M)
    if not m or m.group(1) == "none":
        raise ValueError(f"wiki {arg} has no raw: path")
    return m.group(1)


def _new_page(page_type, slug, raw_rel):
    """A fresh page from the type's template, every {{placeholder}} filled or blanked."""
    body = open(os.path.join(ROOT, "meta", "templates", f"{page_type}.md"), encoding="utf-8").read()
    title = re.sub(r"^[a-z]+-", "", slug).replace("-", " ").title()
    body = body.replace("raw: raw/printed-docs/", f"raw: {raw_rel}")
    if page_type == "video":                          # a scrap-youtube bundle knows its own metadata
        import json
        try:
            with open(os.path.join(ROOT, os.path.dirname(raw_rel), "video.json"), encoding="utf-8") as f:
                meta = json.load(f)
            title = meta.get("title") or title
            body = body.replace("{{url}}", meta.get("url") or "")
            body = body.replace("{{author}}", json.dumps(meta.get("channel") or "", ensure_ascii=False))  # quoted YAML
        except (OSError, ValueError):
            pass
    body = body.replace("{{raw}}", raw_rel).replace("{{title}}", title)
    return re.sub(r"\{\{[a-z_]+\}\}", "", body)


def _add_raw(wiki_path, raw_rel):
    """Append raw_rel to the page's `raw:` (scalar → list) unless already listed. For a page that
    covers several clips — the numbered parts of one blog series."""
    text = open(wiki_path, encoding="utf-8").read()
    m = re.search(r"^raw:\s*(.*)$", text, re.M)
    if not m:
        raise ValueError(f"{wiki_path} has no raw: line")
    val = m.group(1).strip()
    items = [x.strip() for x in val.strip("[]").split(",") if x.strip() and x.strip() != "none"]
    if raw_rel in items:
        return False
    items.append(raw_rel)
    wikiio.write_page(wiki_path, wikiio.set_key(text, "raw", f"[{', '.join(items)}]" if len(items) > 1 else items[0]))
    return True


def _update_wiki_digestion(slug, raw_rel, page_type="paper"):
    """easy = read: depth easy and status digested, on a new or existing page."""
    wiki_path = os.path.join(ROOT, "wiki", f"{slug}.md")
    text = (open(wiki_path, encoding="utf-8").read() if os.path.isfile(wiki_path)
            else _new_page(page_type, slug, raw_rel))
    text = wikiio.set_key(text, "depth", "easy", after="status")    # front matter only
    text = wikiio.set_key(text, "status", "digested")
    wikiio.write_page(wiki_path, text)
    return wiki_path


def _suggest_related(slug):
    """Print related: suggestions from the citation cache. Silent and never fails."""
    try:
        from kb.search import citations
        c = citations.load_cache()
        pid = c["slugs"].get(slug)
        if not pid:
            return
        from kb.lint.lint import parse_frontmatter
        with open(os.path.join(ROOT, "wiki", f"{slug}.md"), encoding="utf-8") as f:
            rel = (parse_frontmatter(f.read()) or {}).get("related") or []
        rows = citations.rank_for(c, pid, exclude=set(rel) | {slug})[:5]
        if rows:
            print("related suggestions (citations): " + ", ".join(f"{r[0]} ({r[1]})" for r in rows))
    except Exception:
        pass


def easy_digest(arg, into=None, tick=True, lint=True):
    """`into`: an existing page that covers this clip too (a series of numbered posts) — the clip
    joins its raw: list and the row is ticked with that page. `tick`/`lint` off: a batch run
    where the orchestrator ticks rows and lints once at the end."""
    raw_rel = _resolve_raw(arg)
    page_type = unit_type_for_raw(raw_rel)
    if page_type == "video" and not raw_rel.endswith("/video.md"):
        raise ValueError(f"{raw_rel}: a video bundle is digested through its video.md")
    slug = unit_slug_for_raw(raw_rel, page_type)
    existing = existing_digest_for_raw(raw_rel)
    if existing:
        slug = os.path.basename(existing)[:-3]
    if into:
        into = into[:-3] if into.endswith(".md") else os.path.basename(into)
        into_path = os.path.join(ROOT, "wiki", f"{into}.md")
        if not os.path.isfile(into_path):
            raise ValueError(f"--into: no wiki page {into!r} — create the series page first")
        if existing and slug != into:
            raise ValueError(f"{raw_rel} is already digested by [[{slug}]]")
        slug = into
        if _add_raw(into_path, raw_rel):
            print(f"added {raw_rel} to raw: of {into}")

    raw_path = os.path.join(ROOT, raw_rel)
    if page_type == "video":
        from .youtube import bundle
        abstract = bundle.abstract(raw_path)          # metadata + chapters + frame text + transcript ends
    else:
        abstract = extract_text(raw_path, max_pages=3) or ""
    sha = sha1_file(raw_rel)
    out_dir = os.path.join(EASY_DIR, sha)
    os.makedirs(out_dir, exist_ok=True)
    abstract_path = os.path.join(out_dir, "abstract.text")
    with open(abstract_path, "w", encoding="utf-8") as f:
        f.write(abstract)

    wiki_path = _update_wiki_digestion(slug, raw_rel, page_type)
    print(f"easy-digest → {abstract_path} ({len(abstract)} chars)")
    print(f"updated {wiki_path} ({page_type}, depth: easy)")

    from . import course
    hub, n, row = course.hub_row_for_raw(raw_rel)
    if hub and tick:
        course.record_row(hub, row["raws"], slug, "easy")
        print(f"ticked [[{hub}]] row {n}")
    elif hub:
        print(f"row {n} of [[{hub}]] left for the batch tick")
    _suggest_related(slug)
    print("Agent: read abstract.text (~2-4k tokens), fill Problem + Main result, then pixi run lint")
    if lint:
        subprocess.run([sys.executable, "-m", "kb.lint.lint"], cwd=ROOT)
    return abstract_path
