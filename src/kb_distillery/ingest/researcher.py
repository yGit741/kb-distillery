"""Index researcher bibliography via Semantic Scholar; catalog star-tier papers only."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from kb_distillery.config import net
from . import catalog, resolve as resolve_mod, scrap
from .paths import ROOT, wiki_slugs, wiki_titles

from kb_distillery.core import links, persons
from kb_distillery.core import wikiio
from kb_distillery.core.schema import make_slug
from kb_distillery.core.schema import is_page_file


def _wiki(p):
    """A bibliography entry's slug is its PDF stem; its wiki page is `paper-<stem>`."""
    return make_slug("paper", p["slug"])

RESEARCHER_ROOT = os.path.join(ROOT, "meta", ".researcher")
SS_BASE = "https://api.semanticscholar.org/graph/v1"
STAR_MIN_CITES = 200
SILVER_MIN_CITES = 50
MAX_CATALOG = 10
SCHOLAR_USER_RE = re.compile(r"scholar\.google\.com/citations\?.*\buser=([^&]+)", re.I)
PAPER_FIELDS = "title,year,citationCount,venue,externalIds,openAccessPdf,url,paperId,authors"
MANIFEST_VERSION = 2


class Ambiguous(Exception):
    """Several Semantic Scholar authors match the query; the caller must pick an id."""

    def __init__(self, hits):
        super().__init__("ambiguous author")
        self.hits = hits
AUTHOR_FIELDS = "name,affiliations,homepage,url,paperCount,hIndex,externalIds"


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_dir(slug):
    return os.path.join(RESEARCHER_ROOT, slug)


def _manifest_path(slug):
    return os.path.join(_session_dir(slug), "manifest.json")


def _session_path(slug):
    return os.path.join(_session_dir(slug), "session.json")


def _slugify_person(name):
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]+", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s or "researcher"


def _slugify_paper(year, title):
    base = re.sub(r"[^\w.\-]+", "-", (title or "untitled").strip()).strip("-").lower()
    base = re.sub(r"-+", "-", base) or "untitled"
    y = str(year or "2000")
    if not re.match(r"^(1[89]|20)\d{2}$", y):
        y = "2000"
    slug = f"{y}-{base}"
    slug = re.sub(r"\.pdf$", "", slug, flags=re.I)
    return slug[:120]


def _tier_emoji(cites):
    if cites is None:
        return "🥉", "other"
    if cites >= STAR_MIN_CITES:
        return "⭐", "star"
    if cites >= SILVER_MIN_CITES:
        return "🥈", "silver"
    return "🥉", "other"


def _ss_headers():
    headers = {"User-Agent": "thesis-wiki-ingest/1.0"}
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if key:
        headers["x-api-key"] = key
    return headers


def _ss_get(path, params=None, retries=3):
    url = f"{SS_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=_ss_headers())
        try:
            with net.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"Semantic Scholar API {e.code}: {body[:300]}")
            if e.code == 429 and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise last_err from e
    raise last_err


def _parse_scholar_url(query):
    m = SCHOLAR_USER_RE.search(query)
    if m:
        return f"https://scholar.google.com/citations?user={m.group(1)}"
    return None


def _resolve_author_id(query):
    q = query.strip()
    if re.fullmatch(r"\d+", q):
        return q, q
    scholar = _parse_scholar_url(q)
    data = _ss_get("/author/search", {"query": q, "limit": 10})
    hits = data.get("data") or []
    if not hits:
        raise ValueError(f"no Semantic Scholar author match for: {q}")
    if len(hits) == 1:
        return hits[0]["authorId"], hits[0].get("name", q)
    # an exact name match wins only when it is unique; otherwise the caller must pick
    ql = q.lower()
    exact = [h for h in hits if h.get("name", "").lower() == ql]
    if len(exact) == 1:
        return exact[0]["authorId"], exact[0]["name"]
    raise Ambiguous(hits[:5])


def _fetch_author(author_id):
    return _ss_get(f"/author/{author_id}", {"fields": AUTHOR_FIELDS})


def _fetch_papers(author_id):
    papers = []
    offset = 0
    limit = 1000
    while True:
        data = _ss_get(
            f"/author/{author_id}/papers",
            {"fields": PAPER_FIELDS, "limit": limit, "offset": offset},
        )
        batch = data.get("data") or []
        papers.extend(batch)
        if not batch or len(batch) < limit:
            break
        offset += len(batch)
        if offset >= 10000:
            break
    return papers


def _paper_entry(raw, slug_counts):
    title = (raw.get("title") or "").strip()
    year = raw.get("year")
    cites = raw.get("citationCount")
    venue = raw.get("venue") or ""
    ext = raw.get("externalIds") or {}
    arxiv = ext.get("ArXiv") or ext.get("arXiv")
    oa = raw.get("openAccessPdf") or {}
    open_pdf = oa.get("url") if isinstance(oa, dict) else None
    slug = _slugify_paper(year, title)
    # dedupe slugs
    if slug in slug_counts:
        slug_counts[slug] += 1
        slug = f"{slug}-{slug_counts[slug]}"
    else:
        slug_counts[slug] = 0
    emoji, tier = _tier_emoji(cites)
    return {
        "slug": slug,
        "title": title,
        "year": year,
        "venue": venue,
        "citation_count": cites,
        "tier": tier,
        "tier_emoji": emoji,
        "arxiv": arxiv,
        "authors": [a.get("name") for a in (raw.get("authors") or []) if a.get("name")],
        "open_pdf_url": open_pdf,
        "url": raw.get("url") or "",
        "semantic_scholar_paper_id": raw.get("paperId") or "",
        "author_count": len(raw.get("authors") or []),
        "source": "scholar",
        "kind": "paper",
        "pin": False,
        "exclude": False,
        "catalog": False,
    }


def _select_catalog_candidates(papers):
    """Star-tier papers, pinned first. A mega-author report (TensorFlow, GPT-4, …) is not the
    person's own work however many citations it has — skipped unless pinned."""
    stars = [p for p in papers if p.get("kind") != "book" and not p.get("exclude")
             and (p.get("pin") or (p.get("tier") == "star"
                                   and (p.get("author_count") or 0) <= persons.MEGA_AUTHORS))]
    stars.sort(key=lambda p: (0 if p.get("pin") else 1, -(p.get("citation_count") or 0), p.get("year") or 0))
    chosen = stars[:MAX_CATALOG]
    slugs = []
    for p in chosen:
        p["catalog"] = True
        slugs.append(p["slug"])
    return slugs


def _person_slug(query, name):
    """An existing person page wins; else the query's name; else the SS display name
    (which drifts: SS says "G. Kalai" for a page the vault calls gil-kalai)."""
    wdir = os.path.join(ROOT, "wiki")
    known = {n[:-3] for n in os.listdir(wdir) if is_page_file(n)} if os.path.isdir(wdir) else set()
    for cand in (_slugify_person(query), _slugify_person(name)):
        if cand in known:
            return cand
    wanted = name.strip().lower()
    for slug in sorted(known):
        with open(os.path.join(wdir, f"{slug}.md"), encoding="utf-8") as f:
            text = f.read(400)
        if "\ntype: person" in text and persons.title_of(text).strip().lower() == wanted:
            return slug
    is_name = not re.fullmatch(r"\d+", query.strip()) and "://" not in query
    return _slugify_person(query if is_name else name)


def upgrade_manifest(m):
    """v1 → v2 in place: handles, item sources, books as 📖 papers. Idempotent."""
    if (m.get("version") or 1) >= MANIFEST_VERSION:
        return m
    handles = {}
    if m.get("homepage"):
        handles["url"] = m["homepage"]
    if m.get("scholar") or m.get("semantic_scholar_url"):
        handles["scholar"] = m.get("scholar") or m["semantic_scholar_url"]
    m["handles"] = handles
    m.setdefault("edges", {})
    for p in m.get("papers", []):
        p.setdefault("source", "scholar")
        p.setdefault("kind", "paper")
        p.setdefault("pin", False)
        p.setdefault("exclude", False)
    for b in m.pop("books", []) or []:
        b.update({"kind": "book", "source": b.get("source", "manual")})
        m["papers"].append(b)
    for c in m.get("courses", []) or []:
        c.setdefault("source", "manual")
    for key in ("roles", "lineage", "repos", "courses", "videos", "writing"):
        m.setdefault(key, [])
    m.setdefault("verified", None)
    m["version"] = MANIFEST_VERSION
    return m


def _build_manifest(query, author_id, author_meta, papers_raw, slug=None):
    slug_counts = {}
    papers = [_paper_entry(p, slug_counts) for p in papers_raw if (p.get("title") or "").strip()]
    papers.sort(key=lambda p: (-(p.get("citation_count") or 0), p.get("year") or 0))
    catalog_slugs = _select_catalog_candidates(papers)
    name = author_meta.get("name") or query
    affiliations = author_meta.get("affiliations") or []
    affiliation = affiliations[0] if affiliations else ""
    slug = slug or _person_slug(query, name)
    scholar = _parse_scholar_url(query) or ""
    handles = {}
    if author_meta.get("homepage"):
        handles["url"] = author_meta["homepage"]
    if scholar or author_meta.get("url"):
        handles["scholar"] = scholar or author_meta["url"]
    return {
        "version": MANIFEST_VERSION,
        "slug": slug,
        "name": name,
        "affiliation": affiliation,
        "homepage": author_meta.get("homepage") or "",
        "scholar": scholar,
        "semantic_scholar_id": author_id,
        "semantic_scholar_url": author_meta.get("url") or "",
        "paper_count": author_meta.get("paperCount"),
        "h_index": author_meta.get("hIndex"),
        "handles": handles,
        "edges": {},
        "roles": [{"from": "", "to": "", "org": affiliation, "role": "", "source": "scholar"}] if affiliation else [],
        "lineage": [],
        "repos": [],
        "courses": [],
        "videos": [],
        "writing": [],
        "papers": papers,
        "catalog_slugs": catalog_slugs,
        "verified": None,
        "verify": {
            "scholar_paper_count": None,
            "semantic_scholar_paper_count": len(papers),
            "verified_at": None,
            "agent_notes": "",
        },
    }


def load_manifest(slug):
    path = _manifest_path(slug)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"no manifest at meta/.researcher/{slug}/manifest.json")
    with open(path, encoding="utf-8") as f:
        return upgrade_manifest(json.load(f))


def save_manifest(slug, manifest):
    os.makedirs(_session_dir(slug), exist_ok=True)
    with open(_manifest_path(slug), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def load_session(slug):
    path = _session_path(slug)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"no session at meta/.researcher/{slug}/session.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_session(slug, data):
    os.makedirs(_session_dir(slug), exist_ok=True)
    with open(_session_path(slug), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def begin(query, slug=None, author_id=None):
    """Open a researcher session and return its slug — or None when the name is ambiguous on
    Semantic Scholar: the top hits are printed and the caller reruns with --author-id."""
    if author_id:
        author_id = str(author_id)
    else:
        try:
            author_id, _ = _resolve_author_id(query)
        except Ambiguous as e:
            print(f"ambiguous author search for {query!r} — rerun with --author-id <id>:")
            for h in e.hits:
                print(f"  {h.get('authorId'):>12}  {h.get('name', '')}  "
                      f"(papers {h.get('paperCount', '?')}, h {h.get('hIndex', '?')})")
            return None
    author_meta = _fetch_author(author_id)
    papers_raw = _fetch_papers(author_id)
    manifest = _build_manifest(query, author_id, author_meta, papers_raw, slug=slug)
    slug = manifest["slug"]
    if os.path.isfile(_session_path(slug)):
        old = load_session(slug)
        if old.get("status") == "open":
            print(f"session already open for {slug}")
            return slug
    if os.path.isfile(_manifest_path(slug)):
        # re-indexing: keep what verify added by hand (roles, lineage, courses, …) and the
        # pin/exclude marks; refresh the Semantic Scholar rows
        old_m = load_manifest(slug)
        marks = {p["slug"]: p for p in old_m.get("papers", [])}
        for p in manifest["papers"]:
            if p["slug"] in marks:
                p["pin"], p["exclude"] = marks[p["slug"]].get("pin", False), marks[p["slug"]].get("exclude", False)
        manifest["papers"] += [p for p in old_m.get("papers", []) if p.get("source") != "scholar"]
        for key in ("roles", "lineage", "repos", "courses", "videos", "writing"):
            manifest[key] = old_m.get(key) or manifest[key]
        manifest["handles"] = {**manifest["handles"], **(old_m.get("handles") or {})}
        manifest["edges"] = old_m.get("edges") or {}
        manifest["email"] = old_m.get("email", "")
        manifest["bibliography_note"] = old_m.get("bibliography_note", "")
        manifest["catalog_slugs"] = _select_catalog_candidates(manifest["papers"])
    save_manifest(slug, manifest)
    save_session(slug, {
        "slug": slug,
        "status": "open",
        "opened_at": _now(),
        "query": query,
    })
    n_cat = len(manifest["catalog_slugs"])
    print(f"researcher session open: {slug}")
    print(f"  papers indexed: {len(manifest['papers'])}")
    print(f"  catalog candidates (⭐ ≥{STAR_MIN_CITES}, max {MAX_CATALOG}): {n_cat}")
    print(f"  manifest: meta/.researcher/{slug}/manifest.json")
    print("  next: agent verify (Wikipedia, homepage, GitHub, YouTube, feed) → index-researcher finalize <slug>")
    return slug


def verify(slug):
    manifest = load_manifest(slug)
    session = load_session(slug)
    if session.get("status") != "open":
        print(f"session {slug} status is {session.get('status')!r}")
        return 1
    v = manifest.get("verify") or {}
    print(f"manifest: meta/.researcher/{slug}/manifest.json")
    print(f"  papers: {len(manifest.get('papers', []))}")
    handles = manifest.get("handles") or {}
    for k in persons.HANDLES:
        print(f"  {k:<10} {handles.get(k, '(not checked)')}")
    edges = manifest.get("edges") or {}
    for k in persons.EDGES:
        print(f"  {k:<10} {edges.get(k, '(not checked)')}")
    for key in ("roles", "lineage", "repos", "courses", "videos", "writing"):
        print(f"  {key:<10} {len(manifest.get(key) or [])} items")
    if v.get("verified_at"):
        print(f"  verified_at: {v.get('verified_at')}")
        print(f"  notes: {v.get('agent_notes', '')}")
    else:
        print("  verify: not yet updated — set every handle (URL | none | unknown) and edge,")
        print("          fill roles/lineage/repos/courses/videos/writing, set verify block, then finalize")
    missing = [k for k in persons.HANDLES + persons.EDGES if k not in {**handles, **edges}]
    if missing:
        print(f"  not yet checked: {', '.join(missing)}")
    return 0


def _paper_url(p):
    return persons.paper_url(p)


def bib_title_cell(p, known):
    """A bibliography row links its wiki page only if one exists (src/kb_distillery/core/persons.py)."""
    return persons.bib_title_cell(p, known)


def person_frontmatter(manifest, page_fm=None):
    """Page frontmatter from the manifest: handles, email, edges, verified. Keys the page
    already states and the manifest does not are kept (a hand-set `github: none` survives)."""
    fm = {k: v for k, v in (page_fm or {}).items() if k in persons.FIELDS}
    fm["type"] = "person"
    fm.update(manifest.get("handles") or {})
    if manifest.get("email"):
        fm["email"] = manifest["email"]
    fm.update(manifest.get("edges") or {})
    if manifest.get("verified"):
        fm["verified"] = str(manifest["verified"])[:10]
    return fm


def cataloged_slugs(manifest, known):
    return [_wiki(p) for p in manifest.get("papers", [])
            if p.get("catalog") and _wiki(p) in known]


def _write_person_wiki(manifest):
    """Write wiki/<slug>.md: generated sections come from the manifest; the head, Why it
    matters here, Meeting log and any custom section of an existing page are kept verbatim."""
    slug = manifest["slug"]
    known = wiki_titles()
    generated = persons.sections_from_manifest(manifest, known, cataloged_slugs(manifest, known))
    wiki_path = os.path.join(ROOT, "wiki", f"{slug}.md")
    if os.path.isfile(wiki_path):
        with open(wiki_path, encoding="utf-8") as f:
            page_fm, body = persons.parse_frontmatter(f.read())
        head, sections = persons.merge(body, generated)
        fm = person_frontmatter(manifest, page_fm)
        verb = "updated"
    else:
        head = f"# {manifest.get('name', slug)}\n\n{manifest.get('affiliation', '')}".rstrip()
        sections = generated + [
            {"title": persons.WHY, "source": None,
             "body": "- `[Topic title](theme-slug.md)` — why this person is in the vault (link a theme or concept)"},
            {"title": persons.LOG, "source": None, "body": "### YYYY-MM-DD\n- Discussed:\n- Action:"},
        ]
        fm = person_frontmatter(manifest)
        verb = "created"
    wikiio.write_page(wiki_path, persons.render(fm, head, sections))      # keeps ## My notes, last
    print(f"{verb} wiki/{slug}.md")
    return wiki_path


def verified_arxiv(paper, expected_authors, fetcher=None, searcher=None):
    """(arxiv_id, how) — the id to download, or (None, why not).

    Semantic Scholar's `externalIds.ArXiv` is sometimes another paper's: 35 PDFs in this vault
    were downloaded from such ids and sat as `digested` for months. So the record behind the id
    is fetched and accepted only if it looks like this paper (`same_paper`: a known author or
    most of the title); otherwise a title search with the expected authors decides, and if that
    finds nothing the paper is skipped rather than guessed. Raises ArxivUnavailable."""
    from . import arxiv_meta
    fetch = fetcher or arxiv_meta.fetch
    search = searcher or arxiv_meta.search_title
    aid = paper.get("arxiv")
    title = paper.get("title") or ""
    if aid:
        meta = fetch([aid], strict=True).get(aid)
        if meta and arxiv_meta.same_paper(meta, expected_authors, title):
            return aid, "ok"
    hit = search(title, expected_authors) if title else None
    if hit:
        return hit["id"], "fixed" if aid else "found"
    return None, "mismatch" if aid else "none"


def _catalog_paper(person_slug, paper, expected_authors=()):
    from . import arxiv_meta
    slug = paper["slug"]
    result = resolve_mod.resolve(slug)
    if result.status == "found":
        print(f"  skip catalog {slug}: already in vault")
        return "duplicate", slug

    inbox_rel = None
    pdf_url = paper.get("open_pdf_url")
    expected = list(paper.get("authors") or []) + list(expected_authors)
    try:
        arxiv, how = verified_arxiv(paper, expected)
    except arxiv_meta.ArxivUnavailable as e:
        print(f"  skip catalog {slug}: arXiv unavailable — {e}")
        return "scrap_failed", slug
    if how == "fixed":
        print(f"  {slug}: Semantic Scholar's arXiv:{paper.get('arxiv')} is another paper — "
              f"using arXiv:{arxiv} found by title")
        paper["arxiv"], paper["url"] = arxiv, f"https://arxiv.org/abs/{arxiv}"
    elif how == "mismatch":
        print(f"  skip catalog {slug}: arXiv:{paper.get('arxiv')} is not this paper and no "
              "confident match by title — look it up by hand")
        return "arxiv_mismatch", slug
    try:
        if arxiv:
            inbox_rel = scrap.scrap(f"https://arxiv.org/abs/{arxiv}")
        elif pdf_url:
            inbox_rel = scrap.scrap(pdf_url)
        else:
            print(f"  skip catalog {slug}: no arXiv or open PDF URL")
            return "no_pdf", slug
    except resolve_mod.DuplicateBlocked:
        print(f"  skip catalog {slug}: duplicate bytes in vault")
        return "duplicate", slug
    except Exception as e:
        print(f"  skip catalog {slug}: scrap failed — {e}")
        return "scrap_failed", slug

    if arxiv:
        got = arxiv_meta.stamp(os.path.join(ROOT, inbox_rel))
        if got and got != arxiv:
            os.remove(os.path.join(ROOT, inbox_rel))
            print(f"  skip catalog {slug}: downloaded PDF is stamped arXiv:{got}, not {arxiv} — discarded")
            return "wrong_pdf", slug

    try:
        catalog.catalog_paper(
            inbox_rel,
            collection=person_slug,
            slug=slug,
            title=paper.get("title"),
            year=paper.get("year"),
            url=paper.get("url") or "",
        )
        return "cataloged", slug
    except Exception as e:
        print(f"  skip catalog {slug}: catalog failed — {e}")
        return "catalog_failed", slug


def finalize(slug):
    manifest = load_manifest(slug)
    session = load_session(slug)
    if session.get("status") != "open":
        print(f"session {slug} status is {session.get('status')!r}, cannot finalize")
        return 1

    person_slug = manifest["slug"]
    _write_person_wiki(manifest)

    results = {"cataloged": [], "duplicate": [], "no_pdf": [], "scrap_failed": [], "catalog_failed": [],
               "arxiv_mismatch": [], "wrong_pdf": []}
    expected_authors = [manifest.get("name") or person_slug.replace("-", " ")]
    for paper in manifest.get("papers", []):
        if not paper.get("catalog"):
            continue
        status, pslug = _catalog_paper(person_slug, paper, expected_authors)
        results[status].append(pslug)
    save_manifest(slug, manifest)          # ids corrected by title search persist

    subprocess.run(
        [sys.executable, "-m", "kb_distillery.lint.lint"],
        cwd=ROOT,
        check=False,
    )

    session["status"] = "closed"
    session["closed_at"] = _now()
    session["catalog_results"] = results
    save_session(slug, session)

    print(f"\nfinalize complete: wiki/{person_slug}.md")
    print(f"  cataloged: {len(results['cataloged'])}")
    if results["cataloged"]:
        print("   ", ", ".join(results["cataloged"]))
    for key in ("duplicate", "no_pdf", "scrap_failed", "catalog_failed", "arxiv_mismatch", "wrong_pdf"):
        if results[key]:
            print(f"  {key}: {', '.join(results[key])}")
    return 0




def _manifest_for_person(person_slug):
    """Session dirs are not always named after the person (g-kalai → gil-kalai)."""
    if not os.path.isdir(RESEARCHER_ROOT):
        return None
    for name in sorted(os.listdir(RESEARCHER_ROOT)):
        mp = os.path.join(RESEARCHER_ROOT, name, "manifest.json")
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
            if m.get("slug") == person_slug or name == person_slug:
                return m
    return None


def relink_text(text, papers_by_slug, known):
    """Replace dangling links to uncataloged bibliography papers. Pure, so it is testable.
    Valid links and dangling links that are not bibliography papers are left alone."""
    changed = 0

    def dangle(m, target, label):
        nonlocal changed
        if target in known or target not in papers_by_slug:
            return m.group(0)
        changed += 1
        p = dict(papers_by_slug[target])
        if label:
            p["title"] = label
        return bib_title_cell(p, known)

    def sub_wiki(m):
        return dangle(m, m.group(1).strip(), (m.group(2) or "").strip())

    def sub_page(m):
        label, target, _anchor = links.link_parts(m)
        return dangle(m, target, label.strip())

    text = links.WIKILINK.sub(sub_wiki, text)          # a wikilink left in My notes reads as before
    return links.PAGE_LINK.sub(sub_page, text), changed


def relink(person_slug, dry_run=False):
    """Repair a person page in place: uncataloged papers become titles (linked out), not dead links."""
    manifest = _manifest_for_person(person_slug)
    if not manifest:
        print(f"no researcher manifest for {person_slug}", file=sys.stderr)
        return 1
    path = os.path.join(ROOT, "wiki", f"{person_slug}.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    papers = {_wiki(p): p for p in manifest.get("papers", [])}
    new, n = relink_text(text, papers, wiki_titles())
    print(f"{person_slug}: {n} dangling bibliography links → titles"
          + (" (dry run)" if dry_run else ""))
    if n and not dry_run:
        wikiio.write_page(path, new)
    return 0


def abort(slug):
    session = load_session(slug)
    if session.get("status") != "open":
        print(f"session {slug} status is {session.get('status')!r}")
        return 1
    sdir = _session_dir(slug)
    if os.path.isdir(sdir):
        shutil.rmtree(sdir)
    print(f"aborted researcher session {slug}")
    return 0


def status():
    if not os.path.isdir(RESEARCHER_ROOT):
        print("no researcher sessions")
        return 0
    for name in sorted(os.listdir(RESEARCHER_ROOT)):
        sp = _session_path(name)
        if not os.path.isfile(sp):
            continue
        with open(sp, encoding="utf-8") as f:
            s = json.load(f)
        print(f"{name}\t{s.get('status')}\t{s.get('opened_at', '')}")
    return 0
