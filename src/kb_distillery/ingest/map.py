"""Build plan.json from claims.json — entity mapping against wiki slugs."""
import json
import os
import re
import sys

from kb_distillery.lint.lint import parse_frontmatter
from .paths import ROOT, load_session, save_session, session_dir, wiki_slugs, person_from_raw
from .schemas import validate_claims
from .verify import existing_digest_for_raw

from kb_distillery.vault.schema import TOPIC_PREFIX, TOPIC_SLUGS, unit_slug_for_raw, unit_type_for_raw


def _kebab(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _load_aliases():
    path = os.path.join(ROOT, "meta", "aliases.tsv")
    aliases = {}
    if not os.path.isfile(path):
        return aliases
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                aliases[parts[0].lower()] = parts[1].strip()
    return aliases


def _themes_for_areas(areas, known):
    themes = []
    for a in areas or []:
        bare = a[len(TOPIC_PREFIX):] if a.startswith(TOPIC_PREFIX) else a
        if TOPIC_SLUGS and bare not in TOPIC_SLUGS:   # no `[types] areas` declared = any area
            continue
        candidate = f"{TOPIC_PREFIX}{bare}"
        if candidate in known:
            themes.append(candidate)
    return themes


def _match_questions(open_questions, known):
    updates = []
    for qtext in open_questions or []:
        qslug = "q-" + _kebab(qtext)[:60].rstrip("-")
        if qslug in known:
            updates.append({"action": "link_existing", "slug": qslug, "text": qtext})
        else:
            updates.append({"action": "create", "slug": qslug, "text": qtext})
    return updates


def _existing_page(raw, page_type, wiki_slug):
    """Deepening a source that already has a page (an easy blog post, say) rewrites THAT page — its own slug and
    type — instead of planning a second one by the raw file's naming rule."""
    rel = existing_digest_for_raw(raw)
    if not rel:
        return page_type, wiki_slug
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        fm = parse_frontmatter(f.read()) or {}
    return str(fm.get("type") or page_type), os.path.basename(rel)[:-3]


def run_map(sha, no_questions=False):
    """`no_questions`: a bulk digest leaves `open_questions` in claims.json but spawns no q- stub from them."""
    session = load_session(sha)
    claims_path = os.path.join(session_dir(sha), "claims.json")
    if not os.path.isfile(claims_path):
        raise FileNotFoundError("claims.json missing — run extract first")

    with open(claims_path, encoding="utf-8") as f:
        claims = json.load(f)
    validate_claims(claims)

    known = wiki_slugs()
    aliases = _load_aliases()
    link_existing = {}
    create_concepts = []
    aliases_resolved = []
    theme_areas = []

    for concept in claims.get("concepts", []):
        c = concept.strip()
        key = c.lower()
        bare = key[len(TOPIC_PREFIX):] if key.startswith(TOPIC_PREFIX) else key
        if bare in TOPIC_SLUGS:                 # a theme is an `area:`, never a concept stub
            theme_areas.append(bare)
            continue
        if key in aliases:
            slug = aliases[key]
            aliases_resolved.append({"mention": c, "slug": slug})
        else:
            slug = _kebab(c)
        if slug in known:
            link_existing[c] = slug
        elif slug not in [x.get("slug") for x in create_concepts]:
            create_concepts.append({"slug": slug, "mention": c})

    scope = session.get("scope") or {}
    book = scope.get("book")
    page_type = scope.get("unit_type") or unit_type_for_raw(claims["raw"])
    wiki_slug = unit_slug_for_raw(claims["raw"], page_type)
    if book:
        from kb_distillery.ingest.sources.books.book import part_slug
        page_type = "part"
        # a chapter digested again (--redo) keeps its page: the slug its row already links
        wiki_slug = scope.get("slug") or part_slug(book, scope.get("label") or "", scope.get("chapter"))
    else:
        page_type, wiki_slug = _existing_page(claims["raw"], page_type, wiki_slug)
    person = claims.get("person") or person_from_raw(claims["raw"])
    areas = list(dict.fromkeys(theme_areas + [c for c in claims.get("concepts", [])
                                              if c not in theme_areas]))[:5]
    link_slugs = list(claims.get("link_concepts") or [])[:5]
    moc_list = _themes_for_areas(areas, known)

    moc_updates = []
    for moc in moc_list:
        moc_updates.append({"moc": moc, "section": "Papers", "link": book or wiki_slug})

    plan = {
        "wiki_slug": wiki_slug,
        "type": page_type,
        "book": book,
        "hub": scope.get("hub"),
        "hub_row": scope.get("row"),
        "raws": scope.get("raws") or [claims["raw"]],
        "person": person,
        "depth": session.get("depth", "full"),
        "link_existing": link_existing,
        "create_concepts": create_concepts,
        "moc_updates": moc_updates,
        "question_updates": [] if no_questions else _match_questions(claims.get("open_questions"), known),
        "aliases_resolved": aliases_resolved,
        "areas": areas,
        "link_slugs": link_slugs,
    }

    plan_path = os.path.join(session_dir(sha), "plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
        f.write("\n")

    wiki_rel = f"wiki/{wiki_slug}.md"
    new_files = [wiki_rel]
    for c in create_concepts:
        new_files.append(f"wiki/{c['slug']}.md")
    for q in plan["question_updates"]:
        if q.get("action") == "create":
            new_files.append(f"wiki/{q['slug']}.md")
    session["new_files"] = list(dict.fromkeys(new_files))
    for moc in moc_list:
        mrel = f"wiki/{moc}.md"
        if mrel not in session.get("modified_files", []):
            session.setdefault("modified_files", []).append(mrel)
    save_session(sha, session)
    print(f"wrote plan.json — {page_type} {wiki_slug}, {len(moc_updates)} theme update(s)")
    return plan
