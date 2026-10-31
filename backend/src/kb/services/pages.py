"""Data for the Explore reader: page index, single pages, search, paths (0 LLM)."""
import math
import os
import re
import sys
from collections import deque
from datetime import datetime, timezone

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")

from kb.core.graph import outbound_links
from kb.search.semfind import load_pages
from kb.services.graph import _areas, _preview, _title, _year
from kb.core.summary import unquote
from kb.search import qmd_client
from kb.storage import raw

ROOT = vault_root()
WIKILINK = re.compile(r"\[\[([^\]|#\\]+)(?:#[^\]|]+)?(?:\\?\|([^\]]+))?\]\]")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
MAX_PATHS = 4
MAX_SUGGESTIONS = 6
RELATED_FLAG = "semantic-search"
RELATED_MAX = 8          # meaning-based hits shown under the keyword hits
RELATED_PER_COLLECTION = 3   # so one big series (738 Kalai posts) can't fill the list


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _body(text):
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            return parts[1].lstrip("\n")
    return text


_TITLES = {}


def _plain(s, titles=None):
    titles = _TITLES if titles is None else titles
    s = WIKILINK.sub(lambda m: (m.group(2) or titles.get(m.group(1).strip()) or m.group(1)).strip(), s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[*_`>#]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _clip(s, centre, width=220):
    if len(s) <= width:
        return s
    start = max(0, centre - width // 2)
    end = min(len(s), start + width)
    start = max(0, end - width)
    out = s[start:end]
    if start > 0:
        out = "…" + out.lstrip()
    if end < len(s):
        out = out.rstrip() + "…"
    return out


def _words(text):
    return len(_body(text).split())


def _mtime(rel, root=None):
    try:
        return int(os.stat(os.path.join(root or ROOT, rel)).st_mtime)
    except OSError:
        return 0


def _as_list(v):
    if not v:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v if x]


def _link_context(text, fm, target, titles=None):
    """Sentence-ish snippet of `text` showing why it links to `target`."""
    titles = _TITLES if titles is None else titles
    needle = f"[[{target}"
    heading = ""
    for line in _body(text).splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
        pos = line.find(needle)
        if pos < 0:
            continue
        where = f" under “{heading}”" if heading else ""
        if line.lstrip().startswith("|"):
            return f"listed in a table{where}"
        plain = re.sub(r"^[-*]\s+", "", _plain(line, titles))
        bare = re.sub(r"^[-*\d.\s]+", "", plain)
        if len(bare) <= len(titles.get(target, target)) + 12:
            return f"listed{where}" if where else "listed"
        label = _plain(line[pos:line.find("]]", pos) + 2], titles)
        centre = plain.find(label) if label else 0
        return _clip(plain, max(centre, 0))
    if target in _as_list(fm.get("related")) or target in _as_list(fm.get("recommended_by")):
        return "listed in frontmatter"
    return ""


def _titles(pages):
    return {s: _title(t, s) for s, (_r, _f, t) in pages.items()}


def _graph(pages, titles=None):
    """(out, in, wanted) link maps; refreshes the shared `_TITLES` unless the caller keeps its own `titles`."""
    if titles is None:
        _TITLES.clear()
        _TITLES.update(_titles(pages))
    out = {}
    wanted = {}
    for slug, (_rel, fm, text) in pages.items():
        links = outbound_links(text, fm) - {slug}
        out[slug] = {t for t in links if t in pages}
        for t in links:
            if t and t not in pages:
                wanted.setdefault(t, set()).add(slug)
    inn = {s: set() for s in pages}
    for s, targets in out.items():
        for t in targets:
            inn[t].add(s)
    return out, inn, wanted


def _card(slug, pages, out, inn, root=None):
    rel, fm, text = pages[slug]
    return {
        "id": slug,
        "title": _title(text, slug),
        "type": fm.get("type", "unknown"),
        "status": fm.get("status", ""),
        "depth": fm.get("depth", ""),
        "areas": _areas(fm),
        "year": _year(slug, fm),
        "in": len(inn[slug]),
        "out": len(out[slug]),
        "words": _words(text),
        "mtime": _mtime(rel, root),
        "preview": _preview(text, 320),
    }


def build_index(view=None):
    """Every page as a card, of the active knowledge base or of `view` (a `kbview.KbView`)."""
    root = view.root if view else None
    pages = load_pages(root)
    out, inn, wanted = _graph(pages, _titles(pages) if view else None)
    cards = [_card(s, pages, out, inn, root) for s in sorted(pages)]
    links = [[s, t] for s in sorted(out) for t in sorted(out[s])]
    wanted_rows = sorted(
        ({"id": t, "count": len(src), "from": sorted(src)[:6]} for t, src in wanted.items()),
        key=lambda r: (-r["count"], r["id"]),
    )
    return {
        "generated_at": _now(),
        "pages": cards,
        "links": links,
        "wanted": wanted_rows[:40],
        "wanted_total": len(wanted_rows),
    }


def _suggest(slug, out, inn):
    """Pages that share neighbours with `slug` but are not linked to it (Adamic-Adar)."""
    nbrs = {s: out[s] | inn[s] for s in out}
    mine = nbrs[slug]
    scores = {}
    for mid in mine:
        deg = len(nbrs[mid])
        if deg < 2:
            continue
        w = 1.0 / math.log(deg + 1)
        for cand in nbrs[mid]:
            if cand == slug or cand in mine:
                continue
            row = scores.setdefault(cand, [0.0, []])
            row[0] += w
            row[1].append(mid)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    return [
        {"id": c, "score": round(sc, 2), "via": sorted(via, key=lambda v: len(nbrs[v]))[:3], "shared": len(via)}
        for c, (sc, via) in ranked[:MAX_SUGGESTIONS]
        if len(via) >= 2
    ]


def build_page(slug, view=None):
    """One page of the active knowledge base, or of `view` (a `kbview.KbView`; read-only when not active)."""
    root = view.root if view else None
    pages = load_pages(root)
    if slug not in pages:
        return None
    titles = _titles(pages)
    out, inn, _wanted = _graph(pages, titles)
    rel, fm, text = pages[slug]
    all_out = outbound_links(text, fm) - {slug}
    backlinks = [
        {"id": s, "context": _link_context(pages[s][2], pages[s][1], slug, titles)}
        for s in sorted(inn[slug], key=lambda s: (-len(inn[s]), s))
    ]
    fm_clean = {}
    for k, v in fm.items():
        if v in (None, "", []):
            continue
        fm_clean[k] = v if isinstance(v, list) else str(v)
    return {
        "card": _card(slug, pages, out, inn, root),
        "kb": view.id if view else _active_id(),
        "read_only": bool(view and not view.active),
        "path": rel,
        "frontmatter": fm_clean,
        "markdown": _body(text),
        "backlinks": backlinks,
        "outbound": sorted(out[slug]),
        "broken": sorted(t for t in all_out if t and t not in pages),
        "suggested": _suggest(slug, out, inn),
    }


def _active_id():
    from kb import paths
    return paths.KB.id if paths.KB else ""


def search(query, limit=40):
    q = (query or "").strip().lower()
    if len(q) < 2:
        return {"query": query, "total": 0, "hits": [], "related": []}
    terms = [t for t in re.split(r"\s+", q) if t]
    pages = load_pages()
    _graph(pages)
    hits = []
    for slug, (_rel, fm, text) in pages.items():
        title = _title(text, slug)
        body = _body(text)
        low_title, low_body, low_slug = title.lower(), body.lower(), slug.lower()
        if not all(t in low_title or t in low_body or t in low_slug for t in terms):
            continue
        score = 0
        for t in terms:
            if t in low_title or t in low_slug:
                score += 50
            score += min(low_body.count(t), 12)
        if q in low_title:
            score += 40
        snippet = ""
        for line in body.splitlines():
            low = line.lower()
            if any(t in low for t in terms) and not line.lstrip().startswith(("#", "|")):
                plain = _plain(line)
                pos = min((plain.lower().find(t) for t in terms if t in plain.lower()), default=0)
                snippet = _clip(plain, pos, 240)
                break
        hits.append({
            "id": slug,
            "title": title,
            "type": fm.get("type", "unknown"),
            "depth": fm.get("depth", ""),
            "snippet": snippet or _preview(text, 200),
            "score": score,
        })
    hits.sort(key=lambda h: (-h["score"], h["id"]))
    out = {"query": query, "total": len(hits), "hits": hits[:limit], "related": []}
    if _flag_on(RELATED_FLAG):
        out["related"] = related(query, pages, {h["id"] for h in out["hits"]})
    return out


def _flag_on(name):
    """Effective runtime value (registry + this server's override); a test's forced state wins."""
    from kb.flags import registry
    from kb.services import flags
    forced = registry.forced(name)
    if forced is not None:
        return forced
    try:
        return next(f["value"] for f in flags.list_flags()["flags"] if f["name"] == name)
    except Exception:                                    # unreadable registry: the safe side is off
        return False


def _collection(fm):
    """The series/book/course a source belongs to, for the per-collection cap ('' = none)."""
    for k in ("blog", "book", "course", "series"):
        if fm.get(k):
            return f"{k}:{unquote(str(fm[k]))}"
    return ""


def related(query, pages, exclude=()):
    """Meaning-based hits from the qmd service (title + summary cards), not already among the keyword
    hits, at most RELATED_PER_COLLECTION per collection. [] when the service is down."""
    found = qmd_client.search(query, limit=RELATED_MAX * 3)
    if not found:
        return []
    by_key = {qmd_client.qmd_key(s): s for s in pages}     # qmd renames `a.b` to `a-b`
    out, per = [], {}
    for key, score in found:
        slug = by_key.get(key)
        if not slug or slug in exclude:
            continue
        _rel, fm, text = pages[slug]
        coll = _collection(fm)
        if coll and per.get(coll, 0) >= RELATED_PER_COLLECTION:
            continue
        per[coll] = per.get(coll, 0) + 1
        out.append({"id": slug, "title": _title(text, slug), "type": fm.get("type", "unknown"),
                    "depth": fm.get("depth", ""), "snippet": unquote(fm.get("summary")) or _preview(text, 200),
                    "score": round(score * 100)})
        if len(out) >= RELATED_MAX:
            break
    return out


def find_paths(a, b):
    """Up to MAX_PATHS shortest undirected paths a→b, each hop annotated with its link context."""
    pages = load_pages()
    if a not in pages or b not in pages:
        return None
    out, inn, _wanted = _graph(pages)
    nbrs = {s: out[s] | inn[s] for s in pages}
    dist = {a: 0}
    parents = {a: []}
    dq = deque([a])
    while dq:
        cur = dq.popleft()
        if cur == b:
            break
        for n in sorted(nbrs[cur]):
            if n not in dist:
                dist[n] = dist[cur] + 1
                parents[n] = [cur]
                dq.append(n)
            elif dist[n] == dist[cur] + 1:
                parents[n].append(cur)
    if b not in dist:
        return {"a": a, "b": b, "distance": None, "paths": []}

    paths = []

    def walk(node, tail):
        if len(paths) >= MAX_PATHS:
            return
        if node == a:
            paths.append([a] + tail)
            return
        for p in parents[node]:
            walk(p, [node] + tail)

    walk(b, [])

    def hop(s, t):
        if t in out[s]:
            return {"from": s, "to": t, "dir": "forward", "context": _link_context(pages[s][2], pages[s][1], t)}
        return {"from": s, "to": t, "dir": "back", "context": _link_context(pages[t][2], pages[t][1], s)}

    return {
        "a": a,
        "b": b,
        "distance": dist[b],
        "paths": [
            {"nodes": p, "hops": [hop(p[i], p[i + 1]) for i in range(len(p) - 1)]}
            for p in paths
        ],
    }


CHAT_ASSET_EXT = (".html", ".svg", ".png")


def resolve_chat_asset(rel):
    """An extracted chat visualization under meta/chats/assets/, or None."""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel.lower().endswith(CHAT_ASSET_EXT):
        return None
    root = os.path.join(ROOT, "meta", "chats", "assets") + os.sep
    full = os.path.normpath(os.path.join(ROOT, rel))
    return full if full.startswith(root) and os.path.isfile(full) else None


def resolve_asset(name):
    """Map an Obsidian embed name to a readable image path under raw/, or None (looked up by logical key through the
    kb's storage connector; a key with `..` or a leading `/` names nothing)."""
    name = (name or "").replace("\\", "/").lstrip("/")
    if not name.lower().endswith(IMAGE_EXT):
        return None
    base = os.path.basename(name)
    for key in (name, f"raw/images/{base}", f"raw/web-clips/{base}"):
        if raw.is_raw_key(key) and raw.exists(key):
            return raw.path(key)
    return None
