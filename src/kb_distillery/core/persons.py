"""Person pages: frontmatter handles generate sections. Pure functions, no third-party deps.

A `type: person` page carries three kinds of keys and nothing else:

    url / scholar / github / youtube / blog / wikipedia   handles — each generates one section
    orgs / advisors / students                            graph edges (bare slugs)
    email                                                 contact, no section
    verified: YYYY-MM-DD                                  set by finalize once every handle was checked

A handle is a URL, `none` (checked: the person has no such thing) or `unknown` (checked, could
not be found). A *missing* key means not checked yet. Sections exist iff their handle is not
`none`; each generated heading is followed by `<!-- from: <handle|manual> -->` and only those
sections are rewritten by finalize — `## Why it matters here`, `## Meeting log` and any custom
section are hand-owned and preserved verbatim. Nothing on a person page is `status`-tracked:
progress is the `verified` date, and `--health` counts pages without one.
"""
import re

from kb_distillery.core.schema import CONCEPT_TYPES, make_slug
from kb_distillery.core.links import WIKILINK_TARGET

HANDLES = ("url", "scholar", "github", "youtube", "blog", "wikipedia")
EDGES = ("orgs", "advisors", "students")
CONTACT = ("email",)
SUMMARY_FIELDS = ("summary", "summary_from", "summary_by")   # schema 1.3, every page type (kb_distillery.core.summary)
FIELDS = {"type", "layer", "verified", *HANDLES, *EDGES, *CONTACT, *SUMMARY_FIELDS}
# Keys the pre-0.12 layouts used; migration 0006 moves their content into the body.
LEGACY_FIELDS = ("status", "area", "related", "affiliation", "lab", "role", "optional", "tau_profile")
NONE, UNKNOWN = "none", "unknown"

# (section title, handle that generates it) in page order.
SECTIONS = (
    ("Roles & companies", "wikipedia"),
    ("Academic lineage", "wikipedia"),
    ("Repos", "github"),
    ("Courses", "url"),
    ("Videos & talks", "youtube"),
    ("Writing", "blog"),
    ("Bibliography", "scholar"),
    ("Cataloged in vault", "scholar"),
)
GENERATED = dict(SECTIONS)
WHY, LOG = "Why it matters here", "Meeting log"
MANUAL = "manual"
BIB_CAP = None                    # rows shown on the page (None = all: meta/.researcher is not in git)
MEGA_AUTHORS = 20                 # a paper with more authors is not cataloged unless pinned

MARKER = re.compile(r"^<!--\s*from:\s*([\w-]+)\s*-->\s*$")
LINK = WIKILINK_TARGET
URL = re.compile(r"^https?://\S+$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# -- parsing -----------------------------------------------------------------------------------
def parse_frontmatter(text):
    """Same minimal YAML as lint.parse_frontmatter: flat `key: value` and `key: [a, b]`."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    fm = {}
    for line in text[3:end].splitlines():
        line = line.split("#")[0].rstrip()
        if not line.strip() or ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        fm[k.strip()] = v
    body = text[end + 4:]
    return fm, body.lstrip("\n")


def as_list(v):
    if v is None or v == "":
        return []
    return [v] if isinstance(v, str) else list(v)


def parse_sections(body):
    """`## ` sections of a page body → (head, [{title, source, body}]). `###` stays inside its
    section; `source` is the `<!-- from: x -->` marker right under the heading, else None."""
    head, sections, cur = [], [], None
    for line in body.split("\n"):
        if line.startswith("## "):
            cur = {"title": line[3:].strip(), "source": None, "lines": []}
            sections.append(cur)
            continue
        if cur is None:
            head.append(line)
            continue
        m = MARKER.match(line.strip())
        if m and cur["source"] is None and not any(l.strip() for l in cur["lines"]):
            cur["source"] = m.group(1)
            continue
        cur["lines"].append(line)
    for s in sections:
        s["body"] = "\n".join(s.pop("lines")).strip("\n")
    return "\n".join(head).strip("\n"), sections


def title_of(body):
    for line in body.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return ""


# -- rendering ---------------------------------------------------------------------------------
def render_frontmatter(fm):
    lines = ["---", "type: person", "layer: concept"]
    for k in HANDLES + CONTACT:
        if k in fm:
            lines.append(f"{k}: {fm[k]}")
    for k in EDGES:
        if k in fm:
            lines.append(f"{k}: [{', '.join(as_list(fm[k]))}]")
    if fm.get("verified"):
        lines.append(f"verified: {fm['verified']}")
    return "\n".join(lines) + "\n---\n"


def render_section(title, source, body):
    return f"## {title}\n<!-- from: {source} -->\n\n{body.strip()}\n" if source else f"## {title}\n\n{body.strip()}\n"


def order(sections):
    """Generated sections in SECTIONS order, then Why it matters, custom sections, Meeting log."""
    by_title = {}
    for s in sections:
        by_title.setdefault(s["title"], s)
    out = [by_title[t] for t, _h in SECTIONS if t in by_title]
    if WHY in by_title:
        out.append(by_title[WHY])
    out += [s for s in sections if s["title"] not in GENERATED and s["title"] not in (WHY, LOG)]
    if LOG in by_title:
        out.append(by_title[LOG])
    return out


def render(fm, head, sections):
    parts = [render_frontmatter(fm), "\n" + head.strip() + "\n"]
    for s in order(sections):
        parts.append("\n" + render_section(s["title"], s.get("source"), s["body"]))
    return "".join(parts)


def merge(existing_body, generated):
    """Replace the generated sections of an existing page with `generated` (a list of
    {title, source, body}); hand-owned and custom sections, the head and the Meeting log are
    kept verbatim. A generated title absent from `generated` is removed (its handle is gone)."""
    head, sections = parse_sections(existing_body)
    kept = [s for s in sections if s["title"] not in GENERATED]
    return head, kept + list(generated)


# -- manifest → sections -----------------------------------------------------------------------
def _link(item):
    title, url, wiki = item.get("title", ""), item.get("url", ""), item.get("wiki", "")
    if wiki:
        return f"[[{wiki}|{title}]]" if title and title != wiki else f"[[{wiki}]]"
    return f"[{title}]({url})" if url else title


def _bullet(item):
    s = _link(item)
    if item.get("year"):
        s += f" ({item['year']})"
    if item.get("note"):
        s += f" — {item['note']}"
    return f"- {s}"


def _source_of(items, handle):
    return handle if any(i.get("source") == handle for i in items) else MANUAL


def _table(cols, rows):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(re.sub(r"(?<!\\)\|", r"\\|", str(c)) for c in r) + " |" for r in rows]
    return "\n".join(out)


def paper_url(p):
    if p.get("arxiv"):
        return f"https://arxiv.org/abs/{p['arxiv']}"
    return p.get("url") or p.get("open_pdf_url") or ""


def bib_title_cell(p, known):
    """A bibliography row links its wiki page only if one exists; otherwise the title links out."""
    title = " ".join((p.get("title") or p.get("slug") or "").replace("|", "/").split())  # one table-safe line
    wiki = p.get("wiki") or (make_slug("paper", p["slug"]) if p.get("slug") else "")
    if wiki and wiki in known:
        return f"[[{wiki}\\|{title}]]"   # escaped: a bare | would split the table cell
    url = paper_url(p)
    return f"[{title}]({url})" if url else title


def bib_rows(papers, cap=BIB_CAP):
    """Pinned first, then by citations; excluded papers stay listed (🚫) but are never cataloged."""
    def key(p):
        return (0 if p.get("pin") else 1, -(p.get("citation_count") or 0), p.get("year") or 0)
    rows = sorted([p for p in papers if p.get("kind") != "book"], key=key)
    return rows[:cap] if cap else rows


def row_emoji(p):
    if p.get("pin"):
        return "📌"
    if p.get("exclude") or (p.get("author_count") or 0) > MEGA_AUTHORS:
        return "🚫"
    return p.get("tier_emoji") or "🥉"


def sections_from_manifest(m, known, cataloged=(), cap=BIB_CAP):
    """The generated sections a manifest yields, in page order; empty ones are skipped."""
    out = []

    def add(title, source, body):
        if body.strip():
            out.append({"title": title, "source": source, "body": body})

    roles = m.get("roles") or []
    if roles:
        add("Roles & companies", _source_of(roles, "wikipedia"),
            _table(["From", "To", "Org", "Role"],
                   [(r.get("from") or "?", r.get("to") or "—", r.get("org", ""),
                     (r.get("role") or "—") + (f" · {r['note']}" if r.get("note") else "")) for r in roles]))
    lineage = m.get("lineage") or []
    if lineage:
        rows = []
        for r in lineage:
            who = f"[[{r['slug']}]]" if r.get("slug") and r["slug"] in known else r.get("name", "")
            rows.append((r.get("relation", ""), who, r.get("where", ""), r.get("years", ""), r.get("note", "")))
        add("Academic lineage", _source_of(lineage, "wikipedia"),
            _table(["Relation", "Person", "Where", "Years", "Note"], rows))
    repos = m.get("repos") or []
    if repos:
        add("Repos", _source_of(repos, "github"),
            _table(["Repo", "Stars", "What", "Ingest"],
                   [(_link(r), r.get("metric") or "—", r.get("note", ""), r.get("action") or "index") for r in repos]))
    for title, key, handle in (("Courses", "courses", "url"), ("Videos & talks", "videos", "youtube"),
                               ("Writing", "writing", "blog")):
        items = m.get(key) or []
        if items:
            add(title, _source_of(items, handle), "\n".join(_bullet(i) for i in items))

    papers = m.get("papers") or []
    books = [p for p in papers if p.get("kind") == "book"]
    if papers:
        shown = bib_rows(papers, cap)
        n = len(papers) - len(books)
        head = m.get("bibliography_note") or (
            f"Citations from Semantic Scholar ({n} papers indexed). "
            "⭐ ≥200 · 🥈 50–199 · 🥉 other · 📌 pinned · 🚫 mega-author, not cataloged · 📖 book.")
        if cap and n > cap:
            head += f" Top {cap} shown; the manifest keeps all {n}."
        rows = [(row_emoji(p), p.get("year") or "—", bib_title_cell(p, known), p.get("venue") or "—",
                 p.get("citation_count") if p.get("citation_count") is not None else "—") for p in shown]
        rows += [("📖", b.get("year") or "—", _link(b) + (f" — {b['note']}" if b.get("note") else ""),
                  b.get("venue") or "—", "—") for b in books]
        add("Bibliography", _source_of(papers, "scholar"),
            head + "\n\n" + _table(["", "Year", "Title", "Venue", "Citations"], rows))
    if cataloged:
        add("Cataloged in vault", "scholar", "\n".join(f"- [[{s}]]" for s in cataloged))
    return out


# -- validation --------------------------------------------------------------------------------
def check(slug, fm, body, pages):
    """(errors, warnings, stats) for one person page. `pages` maps slug → frontmatter of every
    wiki page. Trigger rules run only on verified pages; an unverified page is backlog."""
    errors, warnings = [], []
    stats = {"unverified": 0, "unknowns": 0, "stubs": set(), "reciprocal": 0}
    for k in LEGACY_FIELDS:
        if k in fm:
            errors.append(f"`{k}:` is not a person field since schema 0.12 — run the person-v2 migration")
    for k in fm:
        if k not in FIELDS and k not in LEGACY_FIELDS:
            errors.append(f"unknown person field `{k}:` — handles {HANDLES}, edges {EDGES}, email, verified, summary")
    for k in HANDLES:
        v = fm.get(k)
        if v is None:
            continue
        if v == UNKNOWN:
            stats["unknowns"] += 1
        elif v != NONE and not URL.match(str(v)):
            errors.append(f"{k}: must be a URL, `none` or `unknown` (got {v!r})")
    for k in EDGES:
        if k in fm:
            v = fm[k]
            if isinstance(v, str) and v not in (UNKNOWN, ""):
                errors.append(f"{k}: must be a list of slugs, [] or `unknown`")
            elif v == UNKNOWN:
                stats["unknowns"] += 1
    verified = fm.get("verified")
    if verified and not DATE.match(str(verified)):
        errors.append(f"verified: must be YYYY-MM-DD (got {verified!r})")

    head, sections = parse_sections(body)
    titles = [s["title"] for s in sections]
    seen = set()
    for t in titles:
        if t in seen:
            errors.append(f"duplicate section ## {t}")
        seen.add(t)
    if WHY not in titles:
        errors.append(f"missing ## {WHY} — the one hand-written reason this person is in the vault")
    else:
        why = next(s for s in sections if s["title"] == WHY)
        links = [l.strip() for l in LINK.findall(why["body"])]
        # the reason must tie the person to the knowledge: a link to a concept page of this kb (not another person)
        knowledge = frozenset(CONCEPT_TYPES) - {"person"}
        if not any(pages.get(l, {}).get("type") in knowledge for l in links):
            msg = f"## {WHY} links no concept page ({', '.join(sorted(knowledge))})"
            (errors if verified else warnings).append(msg)
    for s in sections:
        t = s["title"]
        if t in GENERATED:
            handle = GENERATED[t]
            if s.get("source") is None:
                errors.append(f"## {t} needs a `<!-- from: {handle}|manual -->` marker under its heading")
            if fm.get(handle) == NONE and s.get("source") != MANUAL:
                errors.append(f"## {t} is generated from `{handle}:` but it is `none`")
            if s.get("source") not in (None, MANUAL) and s["source"] != handle:
                errors.append(f"## {t} is marked from {s['source']} but belongs to `{handle}:`")
    if verified:
        for k in HANDLES + EDGES:
            if k not in fm:
                errors.append(f"verified page must state `{k}:` (a value, `none`/[] or `unknown`)")
        for k in HANDLES:
            if URL.match(str(fm.get(k, ""))) and k != "url":
                if not any(GENERATED.get(t) == k for t in titles):
                    errors.append(f"`{k}:` is set but none of its sections exist — finalize did not run")
    else:
        stats["unverified"] = 1

    for k, back in (("advisors", "students"), ("students", "advisors")):
        for other in as_list(fm.get(k)) if fm.get(k) != UNKNOWN else []:
            ofm = pages.get(other)
            if ofm is None:
                stats["stubs"].add(other)
            elif ofm.get("type") != "person":
                errors.append(f"{k}: [[{other}]] is a {ofm.get('type')} page, not a person")
            elif slug not in as_list(ofm.get(back)):
                stats["reciprocal"] += 1
                warnings.append(f"{k}: [[{other}]] does not list [[{slug}]] under `{back}:`")
    return errors, warnings, stats


def check_all(persons, pages):
    """persons: slug → (fm, body). Returns (errors, warnings, health) with errors as
    (slug, msg) pairs; health = {unverified, unknowns, stubs, reciprocal}."""
    errors, warnings = [], []
    health = {"unverified": 0, "unknowns": 0, "stubs": set(), "reciprocal": 0}
    identity = {}
    for slug, (fm, body) in sorted(persons.items()):
        e, w, s = check(slug, fm, body, pages)
        errors += [(slug, m) for m in e]
        warnings += [(slug, m) for m in w]
        health["unverified"] += s["unverified"]
        health["unknowns"] += s["unknowns"]
        health["reciprocal"] += s["reciprocal"]
        health["stubs"] |= s["stubs"]
        for k in ("scholar", "wikipedia"):
            v = fm.get(k)
            if v and URL.match(str(v)):
                if v in identity and identity[v] != slug:
                    errors.append((slug, f"{k}: {v} is also [[{identity[v]}]]'s — one person, two pages?"))
                identity[v] = slug
    health["stubs"] = sorted(health["stubs"])
    return errors, warnings, health
