"""Person pages v2 (schema 0.12): frontmatter handles generate sections (src/kb_distillery/vault/persons.py).

Every pre-0.12 person page is rewritten without losing a line — reorganised, never deleted:

    affiliation, lab            → first row of ## Roles & companies (manual)
    url / tau_profile, scholar  → handles (a blank url becomes `unknown`; a Scholar link found
                                  in the hand-written bibliography header is promoted)
    role / optional             → the intro sentence ("Candidate thesis instructor.")
    status / area / related     → dropped; every slug not already linked in the body is listed
                                  under ## Why it matters here (moc-* → theme-*)
    ## Research themes, ## Concepts, ## Thesis threads, ### Suggested reading
                                → ## Why it matters here
    ## Books & monographs       → 📖 rows of the bibliography (manifest kind: book)
    ## Teaching                 → ## Courses (manifest items, source: manual)
    ## Blog                     → `blog:` handle + ## Writing
    ## Bibliography             → kept verbatim; hand-written tables also become manifest rows
    custom sections             → kept verbatim after Why it matters here
    ## Meeting log              → kept verbatim

Manifests under meta/.researcher/ are upgraded to v2 and their folder renamed to the page slug.
`python3 src/kb_distillery/migrations/0006_person_v2.py` is a dry run: previews and an accounting report
land in meta/.migrate/person-v2/ and nothing is written to wiki/. apply() refuses when any old
line is unaccounted for.
"""
import json
import os
import re
import shutil
import sys

PRODUCES = (0, 12)
REPORT_DIR = os.path.join("meta", ".migrate", "person-v2")

DROPPED_KEYS = ("status", "area", "related", "role", "optional")
OLD_SECTIONS = {"Research themes", "Concepts", "Thesis threads", "Bibliography",
                "Bibliography (in vault)", "Books & monographs", "Teaching",
                "Cataloged in vault", "Meeting log", "Blog"}
PLACEHOLDERS = ("(none indexed yet)", "(none cataloged yet)", "(add concept links after verify)",
                "See bibliography below", "Star-tier papers with PDF stubs")
SS_SENTENCE = re.compile(r"\s*Indexed from Semantic Scholar \((\d+) papers\)\.?")
ROLE_PHRASE = re.compile(r"\s*·\s*thesis instructor\s*\*\(optional\)\*\.?\s*")
WIKI = re.compile(r"\[\[([^\]|\\]+)(?:\\?\|([^\]]*))?\]\]")
MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
YEAR = re.compile(r"\((\d{4})\)")
SCHOLAR_IN_TEXT = re.compile(r"\[Google Scholar\]\((https?://[^)]+)\)")
URL_IN_TEXT = re.compile(r"https?://[^\s)>\]]+")


def _mods(root):
    from kb_distillery.vault import persons
    from kb_distillery.ingest import researcher
    return persons, researcher


# -- small parsers ---------------------------------------------------------------------------
def _bullets(body):
    items, prose = [], []
    for line in (body or "").split("\n"):
        s = line.strip()
        if not s:
            continue
        (items if s.startswith(("- ", "* ")) else prose).append(s[2:].strip() if s.startswith(("- ", "* ")) else s)
    return items, prose


def _is_placeholder(s):
    return any(p in s for p in PLACEHOLDERS)


def _item(text):
    """`- [title](url) (year) — note` / `- [[slug|label]] — note` / `- title — note` → item."""
    it = {"source": "manual"}
    rest = text.strip()
    m = WIKI.match(rest)
    if m:
        it["wiki"] = m.group(1).strip()
        it["title"] = (m.group(2) or "").strip() or it["wiki"]
        rest = rest[m.end():]
    else:
        m = MD_LINK.match(rest)
        if m:
            it["title"], it["url"] = m.group(1).strip(), m.group(2)
            rest = rest[m.end():]
        else:
            head, sep, tail = rest.partition(" — ")
            it["title"], rest = head.strip(), (sep + tail) if sep else ""
    rest = rest.strip()
    y = YEAR.match(rest)
    if y:
        it["year"] = int(y.group(1))
        rest = rest[y.end():].strip()
    if rest.startswith("—"):
        rest = rest[1:].strip()
    if rest:
        it["note"] = rest
    return it


def _split_sub(body):
    """Section body → (text before the first ###, [(sub-title, sub-body)])."""
    main, subs, cur = [], [], None
    for line in (body or "").split("\n"):
        if line.startswith("### "):
            cur = [line[4:].strip(), []]
            subs.append(cur)
        elif cur is None:
            main.append(line)
        else:
            cur[1].append(line)
    return "\n".join(main).strip("\n"), [(t, "\n".join(l).strip("\n")) for t, l in subs]


def _cells(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _bib_rows(body, researcher):
    """A hand-written bibliography table → (intro lines, manual paper items)."""
    intro, rows, cols = [], [], None
    for line in (body or "").split("\n"):
        s = line.strip()
        if not s:
            continue
        if not s.startswith("|"):
            intro.append(s)
            continue
        cells = _cells(s)
        if cols is None:
            cols = [c.lower() for c in cells]
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        r = dict(zip(cols, cells))
        tcell = r.get("title", "")
        it = {"source": "manual", "kind": "paper", "pin": False, "exclude": False,
              "tier_emoji": cells[0] if cells else "", "venue": r.get("venue", ""),
              "note": r.get("notes", "")}
        yr = r.get("year", "")
        it["year"] = int(yr) if yr.isdigit() else None
        w = WIKI.match(tcell)
        if w:
            it["wiki"] = w.group(1).strip()
            it["title"] = (w.group(2) or "").strip() or it["wiki"]
            it["slug"] = re.sub(r"^paper-", "", it["wiki"])
        else:
            m = MD_LINK.match(tcell)
            it["title"] = m.group(1).strip() if m else tcell
            if m:
                it["url"] = m.group(2)
            it["slug"] = researcher._slugify_paper(it["year"], it["title"])
        c = r.get("citations", "")
        it["citation_count"] = int(c) if c.isdigit() else None
        rows.append(it)
    return intro, rows


# -- vault context ---------------------------------------------------------------------------
def _pages(root, persons):
    """slug → frontmatter of every wiki page (type lookups and link targets)."""
    out = {}
    wdir = os.path.join(root, "wiki")
    for name in os.listdir(wdir):
        if name.endswith(".md"):
            with open(os.path.join(wdir, name), encoding="utf-8") as f:
                fm, _ = persons.parse_frontmatter(f.read())
            out[name[:-3]] = fm or {}
    return out


def _collections(root):
    """person slug → paper page slugs whose corpus row lists that person in `collection`."""
    out = {}
    path = os.path.join(root, "meta", "corpus.tsv")
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if line.startswith("#") or len(parts) < 6 or parts[0] == "path":
                continue
            for c in parts[5].split(","):
                if c.strip() and parts[4]:
                    out.setdefault(c.strip(), set()).add(parts[4])
    return out


def _manifest_dir(root, researcher, slug):
    """(folder name, manifest) for a person — folders were not always named after the page."""
    if not os.path.isdir(researcher.RESEARCHER_ROOT):
        return None, None
    for name in sorted(os.listdir(researcher.RESEARCHER_ROOT)):
        mp = os.path.join(researcher.RESEARCHER_ROOT, name, "manifest.json")
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as f:
                m = json.load(f)
            if m.get("slug") == slug or name == slug:
                return name, m
    return None, None


# -- one page --------------------------------------------------------------------------------
def convert(root, slug, text, persons, researcher, pages, corpus):
    """Old page text → (new text, manifest v2, accounting rows) or None when already v2."""
    fm, body = persons.parse_frontmatter(text)
    if not fm or fm.get("type") != "person" or not any(k in fm for k in persons.LEGACY_FIELDS):
        return None
    known = set(pages)
    head, sections = persons.parse_sections(body)
    sec = {s["title"]: s["body"] for s in sections}
    name = persons.title_of(head) or slug

    _dir, m = _manifest_dir(root, researcher, slug)
    if m:
        m = researcher.upgrade_manifest(m)
    else:
        m = {"version": researcher.MANIFEST_VERSION, "slug": slug, "name": name,
             "affiliation": fm.get("affiliation", ""), "homepage": "", "scholar": "",
             "semantic_scholar_id": "", "paper_count": None, "handles": {}, "edges": {},
             "roles": [], "lineage": [], "repos": [], "courses": [], "videos": [], "writing": [],
             "papers": [], "catalog_slugs": [], "verified": None,
             "verify": {"verified_at": None, "agent_notes": "manifest built by migration 0006 from the hand-written page"}}
    m["slug"], m["name"], m["verified"] = slug, name, None

    bib_body = sec.get("Bibliography") or sec.get("Bibliography (in vault)") or ""
    bib_main, bib_subs = _split_sub(bib_body)
    url = fm.get("url") or fm.get("tau_profile") or persons.UNKNOWN
    sm = SCHOLAR_IN_TEXT.search(bib_main)
    scholar = fm.get("scholar") or (sm.group(1) if sm else persons.UNKNOWN)
    handles = {"url": url, "scholar": scholar}
    blog_body = sec.get("Blog", "")
    if blog_body:
        blog_url = next(iter(URL_IN_TEXT.findall(blog_body)), "")
        for w in WIKI.findall(blog_body):
            if not blog_url:
                blog_url = (pages.get(w[0].strip()) or {}).get("url") or ""
        handles["blog"] = blog_url or persons.UNKNOWN
    m["handles"] = {**(m.get("handles") or {}), **handles}
    if fm.get("email"):
        m["email"] = fm["email"]

    if fm.get("affiliation"):
        org = fm["affiliation"] + (f" · {fm['lab']}" if fm.get("lab") else "")
        row = {"from": "", "to": "", "org": org, "role": "", "source": "manual"}
        if fm.get("tau_profile") and fm.get("tau_profile") != url:
            row["note"] = f"[institutional profile]({fm['tau_profile']})"
        m["roles"] = [row]
    for t in _bullets(sec.get("Teaching", ""))[0]:
        if not _is_placeholder(t):
            it = _item(t)
            if it.get("title") not in {c.get("title") for c in m["courses"]}:
                m["courses"].append(it)
    for b in _bullets(sec.get("Books & monographs", ""))[0]:
        if not _is_placeholder(b):
            it = _item(b)
            it["kind"] = "book"
            if not any(p.get("kind") == "book" and p.get("title") == it.get("title") for p in m["papers"]):
                m["papers"].append(it)
    for b in _bullets(blog_body)[0]:
        it = _item(b)
        if it not in m["writing"]:
            m["writing"].append(it)
    bib_intro, rows = _bib_rows(bib_main, researcher)
    if rows and not any(p.get("source") == "scholar" for p in m["papers"]):
        have = {p.get("wiki") or p.get("slug") for p in m["papers"]}
        m["papers"] += [r for r in rows if (r.get("wiki") or r.get("slug")) not in have]
    ss = SS_SENTENCE.search(head)
    note = " ".join(bib_intro)
    if ss:
        m["paper_count"] = m.get("paper_count") or int(ss.group(1))
        note = (note + f" {ss.group(1)} papers indexed.").strip()
    if note:
        m["bibliography_note"] = note

    new_head = ROLE_PHRASE.sub(". Candidate thesis instructor. ", SS_SENTENCE.sub("", head))
    new_head = re.sub(r"[ \t]+\n", "\n", re.sub(r"  +", " ", new_head)).strip()

    why = []
    themes, prose = _bullets(sec.get("Research themes", ""))
    themes = [t for t in themes if not _is_placeholder(t)]
    if themes or prose:
        why.append("**Themes:**")
        why += [f"- {t}" for t in themes]
        if prose:
            why += [""] + prose
    links = []
    for c in _bullets(sec.get("Concepts", ""))[0]:
        if not _is_placeholder(c):
            w = WIKI.search(c)
            links.append(w.group(1).strip() if w else c)
    extra = [s for s in persons.as_list(fm.get("area")) + persons.as_list(fm.get("related")) if s != slug]
    from kb_distillery.vault.schema import TOPIC_SLUGS as THEME_SLUGS
    extra = [("theme-" + s[4:]) if s.startswith("moc-") else ("theme-" + s) if s in THEME_SLUGS else s
             for s in extra]
    body_links = {l.strip() for l in persons.LINK.findall(body)}
    people = [s for s in dict.fromkeys(links + extra) if pages.get(s, {}).get("type") == "person"]
    concepts = [s for s in dict.fromkeys(links) if s not in people]
    also = [s for s in dict.fromkeys(extra) if s not in people and s not in concepts and s not in body_links]

    def fmt(s):
        return f"[[{s}]]" if s in known else f"`{s}` (no page)"

    for label, group in (("Concepts", concepts), ("Works with", people), ("Also linked", also)):
        if group:
            why += ["", f"**{label}:** " + " · ".join(fmt(s) for s in group)]
    if sec.get("Thesis threads"):
        why += ["", "### Thesis threads", "", sec["Thesis threads"]]
    for t, b in bib_subs:
        why += ["", f"### {t}", "", b]
    why_body = "\n".join(why).strip() or "- (why is this person in the vault? link a theme or concept)"

    cataloged = set(corpus.get(slug, set()))
    cataloged |= {w[0].strip() for w in WIKI.findall(sec.get("Cataloged in vault", ""))}
    cataloged = sorted(s for s in cataloged if s in known)
    gen = [g for g in persons.sections_from_manifest(m, known, cataloged, cap=None) if g["title"] != "Bibliography"]
    if bib_main.strip():
        verbatim = bib_main.strip()
        if ss and bib_intro:
            verbatim = verbatim.replace(bib_intro[0], bib_intro[0] + f" {ss.group(1)} papers indexed.", 1)
        books = [p for p in m["papers"] if p.get("kind") == "book"]
        if books:   # the manifest renders 📖 rows; a verbatim table must carry them too
            ncol = len(_cells(next(l for l in verbatim.split("\n") if l.strip().startswith("|"))))
            for b in books:
                cell = persons._link(b) + (f" ({b['year']})" if b.get("year") else "") \
                    + (f" — {b['note']}" if b.get("note") else "")
                verbatim += "\n| 📖 | " + " | ".join([str(b.get("year") or "—"), cell] + ["—"] * (ncol - 3)) + " |"
        gen.append({"title": "Bibliography", "source": "scholar" if persons.URL.match(scholar) else persons.MANUAL,
                    "body": verbatim})
    custom = [{"title": s["title"], "source": None, "body": s["body"]}
              for s in sections if s["title"] not in OLD_SECTIONS]
    log = sec.get("Meeting log") or "### YYYY-MM-DD\n- Discussed:\n- Action:"
    new_sections = gen + [{"title": persons.WHY, "source": None, "body": why_body}] + custom \
        + [{"title": persons.LOG, "source": None, "body": log}]
    new_text = persons.render(researcher.person_frontmatter(m), new_head, new_sections)
    return new_text, m, _account(text, new_text)


# -- accounting: where did every old line go? --------------------------------------------------
def _norm(s):
    return " ".join(s.split())


def _account(old_text, new_text):
    """[(status, old line)] — status is kept | moved | transformed | restructured | structural |
    dropped: <why> | UNACCOUNTED. Apply refuses on any UNACCOUNTED line."""
    new_n = _norm(new_text)
    out = []
    fm_end = old_text.find("\n---", 3)
    fm_block = old_text[3:fm_end] if old_text.startswith("---") and fm_end > 0 else ""
    for raw in fm_block.split("\n"):
        s = raw.strip()
        if not s or ":" not in s:
            continue
        k, v = (x.strip() for x in s.split(":", 1))
        if k in DROPPED_KEYS:
            out.append(("dropped: agreed (status/area/related/role/optional)", s))
        elif k == "type":
            out.append(("kept", s))
        elif not v:
            out.append(("dropped: empty value", s))
        else:
            vals = [x.strip() for x in v.strip("[]").split(",")] if v.startswith("[") else [v]
            out.append(("moved" if all(_norm(x) in new_n for x in vals if x) else "UNACCOUNTED", s))
    for raw in old_text[fm_end + 4:].split("\n") if fm_block else old_text.split("\n"):
        s = raw.strip()
        if not s or s == "---":
            continue
        if _norm(s) in new_n:
            out.append(("kept", s))
        elif s.startswith("## ") and s[3:].strip() in OLD_SECTIONS:
            out.append(("restructured", s))
        elif s.startswith("|") and set(s) <= set("|-: "):
            out.append(("structural", s))
        elif _is_placeholder(s):
            out.append(("dropped: placeholder", s))
        else:
            t = ROLE_PHRASE.sub(". Candidate thesis instructor. ", SS_SENTENCE.sub("", s))
            t = re.sub(r"  +", " ", t).strip()
            if _norm(t) in new_n:
                out.append(("transformed", s))
                continue
            # re-rendered bullet: every link target and text fragment must survive
            frags = [u for _, u in MD_LINK.findall(s)] + [w for w, _ in WIKI.findall(s)]
            rest = MD_LINK.sub(" ", WIKI.sub(" ", s)).lstrip("-* ")
            frags += [f.strip(" .;:—–-()*") for f in re.split(r" — |\(\d{4}\)", rest)]
            frags = [f for f in frags if len(f) > 3]
            out.append(("moved" if frags and all(_norm(f) in new_n for f in frags) else "UNACCOUNTED", s))
    return out


# -- run ---------------------------------------------------------------------------------------
def plan(root):
    persons, researcher = _mods(root)
    pages = _pages(root, persons)
    corpus = _collections(root)
    results = {}
    for slug in sorted(s for s, fm in pages.items() if fm.get("type") == "person"):
        path = os.path.join(root, "wiki", f"{slug}.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        r = convert(root, slug, text, persons, researcher, pages, corpus)
        if r:
            results[slug] = r
    return results


def write_report(root, results):
    rdir = os.path.join(root, REPORT_DIR)
    os.makedirs(rdir, exist_ok=True)
    lines = ["# person-v2 migration report", ""]
    bad = 0
    for slug, (new_text, _m, rows) in results.items():
        with open(os.path.join(rdir, f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(new_text)
        counts = {}
        for st, _ in rows:
            counts[st.split(":")[0]] = counts.get(st.split(":")[0], 0) + 1
        lines.append(f"## {slug}  " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        for st, line in rows:
            if st != "kept":
                lines.append(f"- `{st}` {line[:160]}")
                bad += st == "UNACCOUNTED"
        lines.append("")
    with open(os.path.join(rdir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return bad


def apply(root):
    persons, researcher = _mods(root)
    results = plan(root)
    if not results:
        return
    bad = write_report(root, results)
    if bad:
        raise RuntimeError(f"{bad} old line(s) unaccounted for — see {REPORT_DIR}/report.md; nothing written")
    for slug, (new_text, m, _rows) in results.items():
        old_dir, _ = _manifest_dir(root, researcher, slug)
        if old_dir and old_dir != slug and not os.path.isdir(researcher._session_dir(slug)):
            shutil.move(os.path.join(researcher.RESEARCHER_ROOT, old_dir), researcher._session_dir(slug))
        researcher.save_manifest(slug, m)
        with open(os.path.join(root, "wiki", f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(new_text)
        print(f"person-v2: wiki/{slug}.md")


if __name__ == "__main__":
    from kb_distillery.config.paths import vault_root
    here = vault_root()
    res = plan(here)
    n_bad = write_report(here, res)
    print(f"dry run: {len(res)} page(s) → {REPORT_DIR}/<slug>.md, {n_bad} unaccounted line(s) (report.md)")
    sys.exit(1 if n_bad else 0)
