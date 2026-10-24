#!/usr/bin/env python3
"""Migrate the vault to the data model: raw/<format>/ × corpus.tsv `collection` × type-prefixed slugs.

    python3 -m kb.maintenance.migrate_model                 dry run: summary + meta/.migrate/plan.json
    python3 -m kb.maintenance.migrate_model --apply         execute (refuses while collections.tsv has TODO)
    python3 -m kb.maintenance.migrate_model --apply --rewrite-think   also rewrite [[links]] inside think/

What it does, in one transaction planned up front (nothing is written in a dry run):
  raw/     papers|notes|slides|mail|chats|web|assets → printed-docs|handwritten|presentations|
           emails|llm-chats|web-clips|images. Flat names `<short>-<topic>.<ext>`; a notes PDF with
           no text layer is handwritten. Byte-identical duplicates collapse to one file.
  corpus   rows carried to new paths; `collection` filled from the old folder (course → hub,
           researcher → person); course/series members become backlog (`queued`) rows.
  wiki/    paper-/book-/part- prefixes; moc-<theme> → theme-<theme>; course MOC + source pages
           merge into course-/series- hubs with a generated ## Contents table; gemini and
           substantive chat pages → conversation-; stub chat/mail pages → _quarantine/. Every
           renamed page keeps its old slug in `aliases:`; links, raw:, book:, related: rewritten;
           digestion-status backfilled on reading units.
Config: meta/migration/collections.tsv (old course folder → hub). Idempotent on a migrated vault.
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

from kb.paths import vault_root
META = os.path.join(vault_root(), "meta")
from kb.core.schema import (DUPE_PREFIX, INK_PREFIX, INK_SUFFIX, MANIFEST,  # noqa: E402
                    MANIFEST_COLS, RAW_CHATS, RAW_EMAILS, RAW_HANDWRITTEN, RAW_IMAGES,
                    RAW_NAME, RAW_PRESENTATIONS, RAW_PRINTED, RAW_SUBDIRS, RAW_WEB,
                    make_slug)
from kb.core.schema import TOPIC_SLUGS as THEME_SLUGS

# This tool moves a pre-0.10 vault to the 0.x page model (types theme/concept, `digestion-status`,
# disposition `digested`); `pixi run ops -- migrate` then lifts it to the current schema
# (0008_source_model). Its vocabulary is therefore frozen here, not read from schema.py.
DIGESTION_STATUS = {"catalog", "easy", "full", "deep"}
PAPER_LIKE = {"paper", "part", "lecture", "article", "video", "conversation", "ai-chat", "blog-post"}
from kb.core import hubs
from kb.core import wikiio
from kb.lint.lint import parse_frontmatter

OLD_FORMAT = {"papers": RAW_PRINTED, "slides": RAW_PRESENTATIONS, "mail": RAW_EMAILS,
              "chats": RAW_CHATS, "web": RAW_WEB, "assets": RAW_IMAGES}   # notes: by text layer
STUB_WORDS = 100                    # a chat/mail page with less body than this is a stub
DROP_PAGES = {"moc-thesis-directions", "moc-why-things-work"}
HUB_DROP_SECTIONS = {"Raw material", "Scope", "Overview", "Contents"}
LINK = re.compile(r"\[\[([^\]|#\\]+)(#[^\]|\\]*)?((?:\\?\|)[^\]]*)?\]\]")
TICKED = re.compile(r"`(raw/[^`]+)`")
TEXT_LAYER_CHARS = 200


# --------------------------------------------------------------------------
# reading the vault
# --------------------------------------------------------------------------
def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


def walk(root, top):
    out = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, top)):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        out += [os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/")
                for f in filenames if not f.startswith(".")]
    return sorted(out)


def load_pages(root):
    pages = {}
    for rel in walk(root, "wiki"):
        if not rel.endswith(".md") or "excalidraw" in rel or rel.count("/") != 1:
            continue
        text = read(root, rel)
        fm = parse_frontmatter(text)
        if fm:
            pages[os.path.basename(rel)[:-3]] = (rel, fm, text)
    return pages


def load_manifest(root):
    rows = {}
    path = os.path.join(root, MANIFEST)
    if not os.path.isfile(path):
        return rows
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#") or line.startswith("path\t"):
            continue
        parts = line.split("\t") + [""] * len(MANIFEST_COLS)
        rows[parts[0]] = dict(zip(MANIFEST_COLS, parts))
    return rows


def load_config(path):
    cfg = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#") or line.startswith("key\t"):
            continue
        cells = line.split("\t") + [""] * 10
        key, prefix = (cells[0].split(":", 1) + [""])[:2]
        cfg.append({"key": key, "prefix": prefix, "hub": cells[1], "type": cells[2] or "course",
                    "title": cells[3], "short": cells[4], "institution": cells[5],
                    "course_code": cells[6], "semester": cells[7], "lecturer": cells[8],
                    "merge": [m for m in cells[9].split(",") if m]})
    return cfg


def body_of(text):
    return text.split("\n---", 1)[1].lstrip("-\n") if text.startswith("---") else text


def body_words(text):
    return len(re.sub(r"^#.*$", "", body_of(text), flags=re.M).split())


def has_text_layer(full):
    try:
        import fitz
        doc = fitz.open(full)
    except Exception:
        return True
    n = min(doc.page_count, 5) or 1
    chars = sum(len(doc[i].get_text()) for i in range(min(doc.page_count, 5)))
    doc.close()
    return chars / n >= TEXT_LAYER_CHARS


def kebab(s):
    s = s.replace("&", " and ")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "untitled"


def pretty(name):
    """`Lecture 3  - Dynamic Programming.pdf` → `Lecture 3 - Dynamic Programming`."""
    stem = os.path.splitext(name)[0].replace(INK_SUFFIX, "")
    stem = re.sub(r"\.pdf$", "", stem, flags=re.I)
    return " ".join(stem.replace("_", " ").split()) or name


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------
class Plan:
    def __init__(self, root, cfg):
        self.root, self.cfg = root, cfg
        self.raw = {}            # old path → new path
        self.collection = {}     # new path → [slugs]
        self.raw_dupes = {}      # old path → kept new path (byte-identical, file goes to quarantine)
        self.title = {}          # new path → row title
        self.slug = {}           # old slug → new slug (renamed or merged into)
        self.quarantine = set()  # old slugs whose page leaves wiki/ (stub, dropped, merged)
        self.hubs = {}           # hub slug → config row (+ merged slugs)
        self.notes = []          # assumptions / anything a human should look at
        self.chat_trees = {}     # raw chat clip (old path) → meta/chats conversation id
        self.chat_conv = {}      # new ai-chat slug → conversation id

    def cfg_for(self, key, name):
        hit = [c for c in self.cfg if c["key"] == key and (not c["prefix"] or name.startswith(c["prefix"]))]
        if not hit:
            return None
        return max(hit, key=lambda c: len(c["prefix"]))


def plan_raw(plan, manifest, pages):
    root = plan.root
    person = {s for s, (_r, fm, _t) in pages.items() if fm.get("type") == "person"}
    files = [r for r in walk(root, "raw")]
    taken = {}
    inks = []
    for rel in files:
        parts = rel.split("/")
        kind = parts[1] if len(parts) > 2 else ""
        if kind not in OLD_FORMAT and kind != "notes":
            continue                                   # inbox, or already migrated
        name = parts[-1]
        if INK_SUFFIX in name:
            inks.append(rel)
            continue
        key = parts[2] if kind in ("papers", "notes", "slides") and len(parts) == 4 else ""
        coll, short, c = [], "", None
        if kind in ("papers", "notes", "slides") and key:
            if key in person:
                coll = [key]
            else:
                c = plan.cfg_for(key, name)
                if c is None and key not in ("misc",):
                    plan.notes.append(f"no collections.tsv row for raw/{kind}/{key}/ — {rel} gets no collection")
                if c and c["hub"]:
                    coll, short = [c["hub"]], c["short"]
                    plan.hubs.setdefault(c["hub"], dict(c, merge=[]))
                    for m in c["merge"]:
                        if m not in plan.hubs[c["hub"]]["merge"]:
                            plan.hubs[c["hub"]]["merge"].append(m)
        if kind == "notes":
            fmt = RAW_PRINTED if (not name.lower().endswith(".pdf")
                                  or has_text_layer(os.path.join(root, rel))) else RAW_HANDWRITTEN
        else:
            fmt = OLD_FORMAT[kind]
        if kind == "mail":
            new = f"raw/{RAW_EMAILS}/" + "/".join(parts[2:])
        else:
            stem, ext = os.path.splitext(name)
            if kind == "papers" or re.match(RAW_NAME, name):
                newname = name
            else:
                s = kebab(stem)
                newname = f"{s}{ext.lower()}"
            if short and not newname.startswith(f"{short}-") and kind != "papers":
                newname = f"{short}-{newname}"
            new = f"raw/{fmt}/{newname}"
        if new in taken:
            kept_old = taken[new]
            if manifest.get(rel, {}).get("sha1") and \
                    manifest.get(rel, {}).get("sha1") == manifest.get(kept_old, {}).get("sha1"):
                plan.raw_dupes[rel] = new
                plan.collection[new] = list(dict.fromkeys(plan.collection.get(new, []) + coll))
                continue
            base, ext = os.path.splitext(new)
            n = 2
            while f"{base}-{n}{ext}" in taken:
                n += 1
            new = f"{base}-{n}{ext}"
            plan.notes.append(f"name clash, suffixed: {rel} → {new}")
        taken[new] = rel
        plan.raw[rel] = new
        plan.collection[new] = list(dict.fromkeys(plan.collection.get(new, []) + coll))
        plan.title[new] = pretty(name)
    for rel in inks:                                   # an overlay follows its source document
        src = rel.replace(INK_SUFFIX, "")
        src = src if src in plan.raw else re.sub(r"\.pdf\.pdf$", ".pdf", src, flags=re.I)
        if src in plan.raw:
            new_src = plan.raw[src]
            plan.raw[rel] = re.sub(r"\.pdf$", f"{INK_SUFFIX}.pdf", new_src)
        else:
            folder = OLD_FORMAT.get(rel.split("/")[1], RAW_HANDWRITTEN)
            plan.raw[rel] = f"raw/{folder}/{kebab(pretty(os.path.basename(rel)))}{INK_SUFFIX}.pdf"
            plan.notes.append(f"ink overlay without a source: {rel}")


def plan_pages(plan, pages):
    merge_into = {m: hub for hub, c in plan.hubs.items() for m in c["merge"]}
    for c in plan.cfg:                                 # hubs with no raw members still exist
        if c["hub"] and c["merge"]:
            plan.hubs.setdefault(c["hub"], dict(c, merge=list(c["merge"])))
            for m in c["merge"]:
                merge_into.setdefault(m, c["hub"])
    for slug, (_rel, fm, text) in sorted(pages.items()):
        t = fm.get("type")
        if slug in merge_into:
            plan.slug[slug] = merge_into[slug]
            plan.quarantine.add(slug)
        elif slug in DROP_PAGES:
            plan.quarantine.add(slug)
        elif t in ("paper", "book", "part", "lecture", "article", "video", "conversation",
                   "ai-chat", "blog-post", "notebook", "course", "series", "theme"):
            new = make_slug("topic" if t == "theme" else t, slug)
            if new != slug:
                plan.slug[slug] = new
        elif t == "moc":
            bare = slug[len("moc-"):]
            if bare in THEME_SLUGS:
                plan.slug[slug] = f"theme-{bare}"
            else:
                plan.notes.append(f"moc page {slug} is not a theme and has no collections.tsv merge "
                                  "row — quarantined")
                plan.quarantine.add(slug)
        elif t == "source":
            m = re.match(r"^source-(gemini|chat|mail)-(.+)$", slug)
            if not m:
                plan.notes.append(f"source page {slug} has no collections.tsv merge row — quarantined")
                plan.quarantine.add(slug)
                continue
            medium, rest = m.groups()
            if medium != "gemini" and body_words(text) < STUB_WORDS:
                plan.quarantine.add(slug)
                continue
            rest = re.sub(r"-full$", "", rest)
            # a chat with a conversation tree is an ai-chat page; one without (Gemini summaries
            # written by hand, email threads) is a conversation page
            conv = plan.chat_trees.get(str(fm.get("raw") or ""))
            if conv:
                new = f"chat-{rest}"
                plan.chat_conv[new] = conv
            else:
                new = f"conversation-{'mail-' if medium == 'mail' else ''}{rest}"
            if new in plan.slug.values():
                plan.notes.append(f"{slug} collides on {new} — quarantined (alias kept)")
                plan.quarantine.add(slug)
            plan.slug[slug] = new
    # a stub whose `-full` sibling survived resolves to that page, not to plain text
    for slug in list(plan.quarantine):
        full = f"{slug}-full"
        if slug not in plan.slug and full in plan.slug and full not in plan.quarantine:
            plan.slug[slug] = plan.slug[full]


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def rewrite_links(text, plan, unlinked):
    def sub(m):
        target, anchor, label = m.group(1).strip(), m.group(2) or "", m.group(3) or ""
        if target in plan.slug:
            return f"[[{plan.slug[target]}{anchor}{label}]]"
        if target in unlinked:
            shown = label.lstrip("\\|") if label else target
            return shown
        return m.group(0)
    return LINK.sub(sub, text)


def rewrite_paths(text, plan, folder_hub):
    def sub(m):
        p = m.group(1)
        if p in plan.raw:
            return f"`{plan.raw[p]}`"
        if p in plan.raw_dupes:
            return f"`{plan.raw_dupes[p]}`"
        hub = folder_hub.get(p.rstrip("/") + "/")
        return f"[[{hub}]]" if hub else m.group(0)
    return TICKED.sub(sub, text)


def map_raw(v, plan):
    v = v.strip()
    return plan.raw.get(v) or plan.raw_dupes.get(v) or v


def set_fm(text, key, value):
    """Replace (or insert before the closing ---) one flat frontmatter key — front matter only."""
    return wikiio.set_key(text, key, value)


def as_list(v):
    if not v:
        return []
    return v if isinstance(v, list) else [v]


def infer_depth(text):
    if "## Key equations" in text:
        block = text.split("## Key equations", 1)[1].split("\n##", 1)[0].strip()
        if block and block != "—" and len(block) > 8:
            return "full"
    for label in (r"\*\*Problem:\*\*", r"\*\*Main result[^*]*:\*\*"):
        m = re.search(label + r"[ \t]*(\S.*)$", text, re.M)
        if m and len(m.group(1).split()) >= 4:
            return "easy"
    return "catalog"


def render_page(slug, rel, fm, text, plan, unlinked, folder_hub, aliases):
    t = fm.get("type")
    new_slug = plan.slug.get(slug, slug)
    out = rewrite_paths(rewrite_links(text, plan, unlinked), plan, folder_hub)
    if t == "moc":
        out = set_fm(out, "type", "theme")
        t = "theme"
    if t == "source" and new_slug in plan.chat_conv:     # a chat with its tree → ai-chat
        out = set_fm(out, "type", "ai-chat")
        out = re.sub(r"^format:.*\n", "", out, count=1, flags=re.M)
        out = set_fm(out, "conversation", plan.chat_conv[new_slug])
        t = "ai-chat"
    elif t == "source":                                # other surviving source pages: conversations
        medium = "mail" if slug.startswith("source-mail-") else "llm"
        out = set_fm(out, "type", "conversation")
        out = re.sub(r"^format:.*\n", "", out, count=1, flags=re.M)
        out = set_fm(out, "medium", medium)
        if slug.startswith("source-gemini-"):
            out = set_fm(out, "model", "gemini")
        t = "conversation"
    raws = [map_raw(r, plan) for r in as_list(fm.get("raw")) if r]
    if raws:
        out = set_fm(out, "raw", raws[0] if len(raws) == 1 else "[" + ", ".join(raws) + "]")
    if fm.get("book"):
        out = set_fm(out, "book", plan.slug.get(fm["book"], fm["book"]))
    if fm.get("related"):
        rel_new = [plan.slug.get(s, s) for s in as_list(fm["related"]) if s not in unlinked]
        out = set_fm(out, "related", "[" + ", ".join(dict.fromkeys(rel_new)) + "]")
    if t in PAPER_LIKE:
        ds = fm.get("digestion-status")
        if ds not in DIGESTION_STATUS:
            ds = "easy" if t in ("conversation", "ai-chat") else infer_depth(text)
            out = set_fm(out, "digestion-status", ds)
        status = fm.get("status")
        if ds == "catalog" and status == "digested":
            out = set_fm(out, "status", "to-read")
        elif ds != "catalog" and status != "digested":
            out = set_fm(out, "status", "digested")
    old = [a for a in aliases.get(new_slug, []) if a != new_slug]
    if old:
        have = [a.strip("\"' ") for a in as_list(fm.get("aliases"))]
        out = set_fm(out, "aliases", "[" + ", ".join(dict.fromkeys(have + old)) + "]")
    return new_slug, out


def sections(text):
    """[(heading, body)] of `## ` sections; heading None for the intro under the H1."""
    out, head, buf = [], None, []
    for line in body_of(text).split("\n"):
        if line.startswith("## "):
            out.append((head, "\n".join(buf).strip()))
            head, buf = line[3:].strip(), []
        elif line.startswith("# ") and head is None and not buf:
            continue
        else:
            buf.append(line)
    out.append((head, "\n".join(buf).strip()))
    return out


def render_hub(hub, c, plan, pages, unlinked, folder_hub, cited_by, aliases):
    merged = [pages[m] for m in c["merge"] if m in pages]
    merged.sort(key=lambda p: -len(p[2]))
    intro, scope, extra = [], [], {}
    related, area = [], []
    for _rel, fm, text in merged:
        text = rewrite_paths(rewrite_links(text, plan, unlinked), plan, folder_hub)
        related += [plan.slug.get(s, s) for s in as_list(fm.get("related")) if s not in unlinked]
        area += [a for a in as_list(fm.get("area")) if a in THEME_SLUGS]
        for head, body in sections(text):
            if not body:
                continue
            if head is None and not intro:
                intro.append(body)
            elif head in ("Scope", "Overview") and not scope:
                scope.append(body)
            elif head not in HUB_DROP_SECTIONS and head not in extra:
                extra[head] = body
    members = sorted(p for p, cols in plan.collection.items() if hub in cols)
    rows = []
    for p in members:
        if INK_SUFFIX in p:
            continue
        page = cited_by.get(p)
        status, link = hubs.TODO, ""
        if page:
            link = page[0]
            ds = page[1]
            status = ds if ds in ("easy", "full", "deep") else hubs.TODO
        rows.append({"title": plan.title.get(p, os.path.basename(p)), "raws": [p],
                     "status": status, "slug": link})
    fm = ["---", f"type: {c['type']}", f"short: {c['short']}"]
    if c["type"] == "course":
        for k in ("institution", "course_code", "semester", "lecturer"):
            v = c[k] if c[k] not in ("-", "") else ""
            fm.append(f"{k}: {v}")
    else:
        fm.append(f"author: {c['lecturer'] if c['lecturer'] not in ('-', '') else ''}")
    fm += [f"area: [{', '.join(dict.fromkeys(area))}]",
           f"status: {hubs.hub_status(rows)}",
           f"aliases: [{', '.join(a for a in aliases.get(hub, []) if a != hub)}]",
           f"related: [{', '.join(dict.fromkeys(r for r in related if r != hub))}]",
           "---", "", f"# {c['title'] or hub}", "", "## Overview", ""]
    overview = "\n\n".join(intro + scope) or ("<!-- At least one paragraph: what the course "
                                              "covers and why it matters here. -->")
    text = "\n".join(fm) + "\n" + overview + "\n\n" + hubs.CONTENTS_HEADING + "\n\n" + hubs.render(rows) + "\n"
    for head, body in extra.items():
        text += f"\n## {head}\n\n{body}\n"
    if "Threads" not in extra:
        text += "\n## Threads\n"
    return text


def build(root, cfg_path):
    cfg = load_config(cfg_path)
    plan = Plan(root, cfg)
    pages = load_pages(root)
    manifest = load_manifest(root)
    plan_raw(plan, manifest, pages)
    index = os.path.join(root, "meta", "chats", "index.json")
    if os.path.isfile(index):
        plan.chat_trees = json.load(open(index, encoding="utf-8")).get("by_clip", {})
    plan_pages(plan, pages)

    unlinked = {s for s in plan.quarantine if s not in plan.slug}
    folder_hub = {}
    for c in cfg:
        if c["hub"]:
            for kind in ("papers", "notes", "slides"):
                folder_hub.setdefault(f"raw/{kind}/{c['key']}/", c["hub"])
    aliases = {}
    for old, new in plan.slug.items():
        aliases.setdefault(new, []).append(old)

    out_pages = {}                                     # new slug → text
    cited_by = {}                                      # new raw path → (new slug, depth)
    for slug, (rel, fm, text) in sorted(pages.items()):
        if slug in plan.quarantine:
            continue
        new_slug, new_text = render_page(slug, rel, fm, text, plan, unlinked, folder_hub, aliases)
        out_pages[new_slug] = new_text
        nfm = parse_frontmatter(new_text) or {}
        if nfm.get("type") in PAPER_LIKE:
            for r in as_list(nfm.get("raw")):
                cited_by.setdefault(r, (new_slug, nfm.get("digestion-status")))
    for hub, c in sorted(plan.hubs.items()):
        out_pages[hub] = render_hub(hub, c, plan, pages, unlinked, folder_hub, cited_by, aliases)

    # a file cited only by a quarantined stub is backlog again (lint never demotes `digested`)
    cited_now = {r for text in out_pages.values()
                 for r in as_list((parse_frontmatter(text) or {}).get("raw"))}
    rows = {}
    for old, r in manifest.items():
        if old in plan.raw_dupes:
            continue
        new = plan.raw.get(old, old)
        row = dict(r, path=new, kind=new.split("/")[1] if new.count("/") > 1 else r.get("kind", ""))
        coll = plan.collection.get(new)
        if coll is not None:
            row["collection"] = ",".join(coll)
        d = row.get("disposition", "")
        if d.startswith((DUPE_PREFIX, INK_PREFIX)):
            pre, target = d.split(":", 1)
            row["disposition"] = f"{pre}:{plan.raw.get(target, target)}"
        elif any(h in plan.hubs for h in (coll or [])) and d in ("skip", "digested"):
            row["disposition"] = "queued"               # the Contents table decides now
        elif d == "digested" and new not in cited_now:
            row["disposition"] = "queued"
        rows[new] = row
    return plan, pages, out_pages, rows


# --------------------------------------------------------------------------
# reporting and applying
# --------------------------------------------------------------------------
def summary(plan, pages, out_pages, rows):
    by_fmt = {}
    for new in plan.raw.values():
        f = new.split("/")[1]
        by_fmt[f] = by_fmt.get(f, 0) + 1
    renamed = sum(1 for o, n in plan.slug.items() if o not in plan.quarantine)
    merged = sum(1 for o in plan.quarantine if o in plan.slug)
    dropped = sorted(s for s in plan.quarantine if s not in plan.slug)
    lines = [
        f"raw files moved: {len(plan.raw)}  " + "  ".join(f"{k}={v}" for k, v in sorted(by_fmt.items())),
        f"raw byte-identical duplicates collapsed: {len(plan.raw_dupes)}",
        f"collections: " + ", ".join(f"{h} ({sum(1 for c in plan.collection.values() if h in c)})"
                                     for h in sorted({h for c in plan.collection.values() for h in c})),
        f"wiki pages: {len(pages)} → {len(out_pages)}  (renamed {renamed}, merged into hubs {merged}, "
        f"quarantined {len(dropped)}, new hubs {len(plan.hubs)})",
        "hubs: " + ", ".join(sorted(plan.hubs)),
        f"quarantined pages: {', '.join(dropped[:12])}{' …' if len(dropped) > 12 else ''}",
        f"corpus rows: {len(rows)}  queued after migration: "
        f"{sum(1 for r in rows.values() if r.get('disposition') == 'queued')}",
    ]
    if plan.notes:
        lines += ["", f"needs a look ({len(plan.notes)}):"] + [f"  - {n}" for n in plan.notes]
    return "\n".join(lines)


def todo_cells(cfg_path):
    return [line.split("\t")[0] for line in open(cfg_path, encoding="utf-8")
            if not line.startswith("#") and "\tTODO" in line]


def think_hits(root, plan):
    hits = {}
    for rel in walk(root, "think"):
        if not rel.endswith(".md"):
            continue
        n = sum(1 for m in LINK.finditer(read(root, rel)) if m.group(1).strip() in plan.slug
                or m.group(1).strip() in plan.quarantine)
        if n:
            hits[rel] = n
    return hits


def rekey_coherence(root, plan):
    """Warning ids hash their slugs: carry dismissed/fixed/noted statuses to the new slugs."""
    from kb.core.coherence import _hit_id
    path = os.path.join(root, "meta", "coherence-warnings.tsv")
    if not os.path.isfile(path):
        return
    lines = open(path, encoding="utf-8").read().split("\n")
    out = lines[:1]
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 6:
            out.append(line)
            continue
        slugs = sorted({plan.slug.get(s, s) for s in parts[3].split(",") if s})
        parts[3] = ",".join(slugs)
        parts[0] = _hit_id(parts[2], slugs, parts[4])
        out.append("\t".join(parts))
    open(path, "w", encoding="utf-8").write("\n".join(out))


def rewrite_sidecars(root, plan):
    """parsed.md sidecars name their source folder in `derived-from:` — follow the move."""
    for old, new in plan.raw.items():
        if os.path.basename(new) != "parsed.md" or not os.path.isfile(os.path.join(root, new)):
            continue
        text = read(root, new)
        old_dir, new_dir = os.path.dirname(old) + "/", os.path.dirname(new) + "/"
        if old_dir in text:
            open(os.path.join(root, new), "w", encoding="utf-8").write(text.replace(old_dir, new_dir))


def apply(root, plan, pages, out_pages, rows, rewrite_think):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    qdir = os.path.join(root, "_quarantine", f"migration-{stamp}")
    unlinked = {s for s in plan.quarantine if s not in plan.slug}

    # 1. every page that leaves or is renamed is copied out first — nothing is lost
    for slug, (rel, _fm, _text) in pages.items():
        if slug in plan.quarantine or slug in plan.slug:
            dst = os.path.join(qdir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(root, rel), dst)
    # 2. raw files
    for old, new in sorted(plan.raw.items()):
        src, dst = os.path.join(root, old), os.path.join(root, new)
        if old == new or not os.path.exists(src):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
    for old in plan.raw_dupes:
        dst = os.path.join(qdir, old)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(os.path.join(root, old), dst)
    for kind in list(OLD_FORMAT) + ["notes"]:
        top = os.path.join(root, "raw", kind)
        for dirpath, _dirs, _files in os.walk(top, topdown=False):      # children first
            leftovers = [f for f in os.listdir(dirpath) if f != ".DS_Store" and f != ".gitkeep"]
            if not leftovers:
                shutil.rmtree(dirpath)
    for sub in RAW_SUBDIRS:
        os.makedirs(os.path.join(root, "raw", sub), exist_ok=True)
    rewrite_sidecars(root, plan)
    # 3. wiki
    for slug, (rel, _fm, _text) in pages.items():
        if slug in plan.quarantine or slug in plan.slug:
            os.remove(os.path.join(root, rel))
    for slug, text in out_pages.items():
        with open(os.path.join(root, "wiki", f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(text)
    # 4. corpus.tsv
    with open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as f:
        f.write("# Generated by backend/src/kb/lint/lint.py. Edit the `disposition` and `collection` columns only.\n")
        f.write("# disposition: queued | digested | partial | skip | dupe:<path> · "
                "collection: comma-separated hub/person slugs\n")
        f.write("\t".join(MANIFEST_COLS) + "\n")
        for p in sorted(rows):
            f.write("\t".join(rows[p].get(c, "") for c in MANIFEST_COLS) + "\n")
    # 5. knowledge files that hold slugs or raw paths
    al = os.path.join(root, "meta", "aliases.tsv")
    if os.path.isfile(al):
        lines = []
        for line in open(al, encoding="utf-8").read().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2 and not line.startswith("#"):
                parts[1] = plan.slug.get(parts[1].strip(), parts[1])
            lines.append("\t".join(parts))
        open(al, "w", encoding="utf-8").write("\n".join(lines))
    for rel in walk(root, "meta/chats"):
        if rel.endswith(".json"):
            text = read(root, rel)
            new = text
            for old, path in plan.raw.items():
                new = new.replace(old, path)
            if new != text:
                open(os.path.join(root, rel), "w", encoding="utf-8").write(new)
    rekey_coherence(root, plan)
    if rewrite_think:
        for rel in think_hits(root, plan):
            text = read(root, rel)
            open(os.path.join(root, rel), "w", encoding="utf-8").write(rewrite_links(text, plan, unlinked))
    with open(os.path.join(root, "meta", "log.md"), "a", encoding="utf-8") as f:
        f.write(f"\n## [{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}] migrate | data model — "
                f"raw by format, collection column, type-prefixed slugs ({len(plan.raw)} raw files, "
                f"{len(plan.slug)} slugs; originals in `_quarantine/migration-{stamp}/`)\n")
    return qdir


FINISH_FILE = os.path.join("meta", "migration", "0004-finish.json")


def write_finish(root, plan, rows):
    """What the PR cannot carry: gitignored raw files (PDFs) still to move in the primary checkout,
    the corpus rows (corpus.tsv is generated, never committed by ship) and the slug map for the
    coherence statuses. `migrate_model.py --finish` replays it after the merge."""
    data = {"raw": plan.raw, "raw_dupes": plan.raw_dupes, "slug": plan.slug,
            "rows": {p: {c: r.get(c, "") for c in MANIFEST_COLS} for p, r in rows.items()}}
    path = os.path.join(root, FINISH_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    return path


def finish(root):
    """After the schema PR merged: move the primary checkout's untracked raw files to their new
    paths, rebuild corpus.tsv from the migrated rows (keeping rows for files added since) and carry
    coherence statuses to the new slugs. Idempotent — files already moved are skipped."""
    data = json.load(open(os.path.join(root, FINISH_FILE), encoding="utf-8"))
    moved = 0
    for old, new in data["raw"].items():
        src, dst = os.path.join(root, old), os.path.join(root, new)
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.rename(src, dst)
            moved += 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    for old in data["raw_dupes"]:
        src = os.path.join(root, old)
        if os.path.exists(src):
            dst = os.path.join(root, "_quarantine", f"migration-{stamp}", old)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.rename(src, dst)
    for kind in list(OLD_FORMAT) + ["notes"]:
        top = os.path.join(root, "raw", kind)
        for dirpath, _dirs, _files in os.walk(top, topdown=False):      # children first
            if not [f for f in os.listdir(dirpath) if f not in (".DS_Store", ".gitkeep")]:
                shutil.rmtree(dirpath)
    current = load_manifest(root)
    rows = dict(data["rows"])
    for path, row in current.items():                    # rows for files cataloged since the PR
        if path not in rows and path not in data["raw"] and path not in data["raw_dupes"]:
            rows[path] = row
    with open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as f:
        f.write("# Generated by backend/src/kb/lint/lint.py. Edit the `disposition` and `collection` columns only.\n")
        f.write("# disposition: queued | digested | partial | skip | dupe:<path> · "
                "collection: comma-separated hub/person slugs\n")
        f.write("\t".join(MANIFEST_COLS) + "\n")
        for p in sorted(rows):
            f.write("\t".join(rows[p].get(c, "") for c in MANIFEST_COLS) + "\n")

    class _Plan:                                         # rekey_coherence only needs .slug
        slug = data["slug"]
    rekey_coherence(root, _Plan)
    print(f"finish: moved {moved} untracked raw files, wrote {len(rows)} corpus rows, "
          "re-keyed coherence statuses. Next: python3 -m kb.lint.lint")
    return 0


def run_for_migration(root, config=None, rewrite_think=False):
    """backend/src/kb/migrations/0004_data_model.py entry point: refuse placeholders, apply, record finish."""
    config = config or os.path.join(root, "meta", "migration", "collections.tsv")
    todo = todo_cells(config)
    if todo:
        raise RuntimeError(f"meta/migration/collections.tsv still has TODO cells: {', '.join(todo)}")
    plan, pages, out_pages, rows = build(root, config)
    if not plan.raw and not plan.slug:
        print("data model already migrated — nothing to do")
        return
    print(summary(plan, pages, out_pages, rows))
    apply(root, plan, pages, out_pages, rows, rewrite_think)
    print(f"post-merge step recorded in {write_finish(root, plan, rows)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rewrite-think", action="store_true",
                    help="also rewrite [[links]] inside think/ (human-owned — only when asked)")
    ap.add_argument("--allow-todo", action="store_true",
                    help="apply with TODO cells left in collections.tsv (test clones only)")
    ap.add_argument("--root", default=os.path.dirname(META))
    ap.add_argument("--config", default=os.path.join(META, "migration", "collections.tsv"))
    ap.add_argument("--out", default=None, help="where plan.json goes (default <root>/meta/.migrate/)")
    ap.add_argument("--finish", action="store_true",
                    help="after the schema PR merged: move untracked raw files, rebuild corpus.tsv")
    args = ap.parse_args(argv)
    if args.finish:
        return finish(args.root)

    plan, pages, out_pages, rows = build(args.root, args.config)
    print(summary(plan, pages, out_pages, rows))
    hits = think_hits(args.root, plan)
    if hits:
        print(f"\nthink/ links to renamed pages: {sum(hits.values())} in {len(hits)} file(s) — "
              + ("rewriting (--rewrite-think)" if args.rewrite_think
                 else "left alone; old slugs stay in `aliases:` (pass --rewrite-think to fix)"))

    out = args.out or os.path.join(args.root, "meta", ".migrate")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "plan.json"), "w", encoding="utf-8") as f:
        json.dump({"raw": plan.raw, "raw_dupes": plan.raw_dupes, "collection": plan.collection,
                   "slug": plan.slug, "quarantine": sorted(plan.quarantine),
                   "hubs": sorted(plan.hubs), "notes": plan.notes}, f, indent=1)
    if not args.apply:
        print(f"\nDry run — full plan in {os.path.join(out, 'plan.json')}. Re-run with --apply.")
        return 0

    todo = todo_cells(args.config)
    if todo and not args.allow_todo:
        print(f"\nrefusing: collections.tsv still has TODO cells for {', '.join(todo)}", file=sys.stderr)
        return 2
    ingest = os.path.join(args.root, "meta", ".ingest")
    open_sessions = []
    for d in (os.listdir(ingest) if os.path.isdir(ingest) else []):
        sp = os.path.join(ingest, d, "session.json")
        if os.path.isfile(sp) and json.load(open(sp)).get("status") == "open":
            open_sessions.append(d)
    if open_sessions:
        print(f"\nrefusing: open ingest sessions {open_sessions} — finalize or abort first",
              file=sys.stderr)
        return 2
    qdir = apply(args.root, plan, pages, out_pages, rows, args.rewrite_think)
    print(f"\napplied. Originals of every renamed/removed page: {os.path.relpath(qdir, args.root)}/")
    print("Next: python3 -m kb.lint.lint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
