#!/usr/bin/env python3
"""Citation graph of the vault from Semantic Scholar (0 LLM). Cache: .cache/citations.json.

  python3 -m kb_distillery.search.citations fetch [--slug S ...] [--limit N] [--refresh]   (network)
  python3 -m kb_distillery.search.citations neighbors|rank|missing|path|status ...          (offline)
  fetch and missing take --scope scope-x (only that scope's vault papers)
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, deque
from datetime import datetime, timezone

from kb_distillery.paths import vault_root
HERE = os.path.join(vault_root(), "meta")
ROOT = vault_root()

CACHE_REL = os.path.join(".cache", "citations.json")
SS_BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = ("paperId,title,year,citationCount,externalIds,"
          "references.paperId,references.title,references.year,"
          "citations.paperId,citations.title,citations.year")
PAUSE_S = 3.0
RETRIES = 4
RETRY_CODES = {429, 500, 502, 503, 504}
LIST_CAP = 1000
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([a-z\-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})", re.I)
DOI_RE = re.compile(r"(?:doi\.org/|^doi:\s*)(10\.\d{4,9}/[^\s\"'<>]+)", re.I)
S2_URL_RE = re.compile(r"semanticscholar\.org/paper/(?:[^/]+/)?([0-9a-f]{40})")

SLEEP = time.sleep  # patched by tests
_last = 0.0


def cache_path():
    return os.path.join(ROOT, CACHE_REL)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_cache():
    return {"version": 1, "fetched_at": _now(), "papers": {}, "slugs": {}, "misses": {}}


def load_cache(path=None):
    try:
        with open(path or cache_path(), encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        return empty_cache()
    for k, v in empty_cache().items():
        c.setdefault(k, v)
    return c


def save_cache(cache, path=None):
    path = path or cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cache["fetched_at"] = _now()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------- vault

def vault_papers(wiki_dir=None):
    """{slug: {"arxiv": id|None, "doi": str|None, "s2": paperId|None}} for paper/part pages."""
    from kb_distillery.lint.lint import parse_frontmatter
    wiki_dir = wiki_dir or os.path.join(ROOT, "wiki")
    out = {}
    for name in sorted(os.listdir(wiki_dir)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(wiki_dir, name), encoding="utf-8") as f:
            fm = parse_frontmatter(f.read()) or {}
        if fm.get("type") not in ("paper", "part"):
            continue
        url = str(fm.get("url", ""))
        m = ARXIV_RE.search(url)
        arxiv = m.group(1) if m else (str(fm.get("arxiv", "")).strip() or None)
        d = DOI_RE.search(url)
        doi = d.group(1).rstrip(".,)") if d else (str(fm.get("doi", "")).strip() or None)
        s = S2_URL_RE.search(url)
        if arxiv or doi or s:
            out[name[:-3]] = {"arxiv": arxiv, "doi": doi, "s2": s.group(1) if s else None}
    return out


# ---------------------------------------------------------------- network

def _headers():
    h = {"User-Agent": "thesis-wiki-ingest/1.0"}
    key = os.environ.get("S2_API_KEY", "").strip()
    if not key:
        try:
            with open(os.path.expanduser("~/.config/thesis-kb/keys/s2")) as f:
                key = f.read().strip()
        except OSError:
            pass
    if key:
        h["x-api-key"] = key
    return h


def http_get(path, params=None):
    """Throttled GET returning parsed JSON, or None on 404. Raises RuntimeError otherwise."""
    global _last
    from kb_distillery.ingest import net
    url = SS_BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    last = None
    for attempt in range(1, RETRIES + 1):
        wait = _last + PAUSE_S - time.monotonic()
        if wait > 0:
            SLEEP(wait)
        _last = time.monotonic()
        try:
            req = urllib.request.Request(url, headers=_headers())
            with net.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = RuntimeError(f"HTTP {e.code}")
            if e.code not in RETRY_CODES:
                raise last from e
            try:
                delay = float(e.headers.get("Retry-After", "")) if e.headers else 0
            except ValueError:
                delay = 0
            delay = delay or 5.0 * 2 ** (attempt - 1)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last, delay = RuntimeError(str(e)), 5.0 * attempt
        if attempt < RETRIES:
            print(f"s2: {last} - retry {attempt}/{RETRIES - 1} in {delay:.0f}s", file=sys.stderr)
            SLEEP(delay)
    raise last


def _lookup_id(info):
    if info.get("s2"):
        return info["s2"]
    if info.get("arxiv"):
        return "arXiv:" + info["arxiv"]
    return "DOI:" + info["doi"]


def _node(d, slug=None):
    ext = d.get("externalIds") or {}
    refs = [r["paperId"] for r in (d.get("references") or [])[:LIST_CAP] if r and r.get("paperId")]
    cits = [r["paperId"] for r in (d.get("citations") or [])[:LIST_CAP] if r and r.get("paperId")]
    return {"slug": slug, "title": d.get("title") or "", "year": d.get("year"),
            "arxiv": ext.get("ArXiv"), "doi": ext.get("DOI"),
            "citationCount": d.get("citationCount") or 0,
            "references": refs, "citations": cits, "fetched_at": _now()}


def _stub(r, cache):
    pid = r.get("paperId")
    if pid and pid not in cache["papers"]:
        cache["papers"][pid] = {"slug": None, "title": r.get("title") or "", "year": r.get("year"),
                                "arxiv": None, "doi": None, "citationCount": 0,
                                "references": [], "citations": [], "fetched_at": _now()}


def fetch_one(cache, info, slug=None, http=None):
    """Fetch one paper into the cache; returns paperId or None."""
    http = http or http_get
    d = http("/paper/" + urllib.parse.quote(_lookup_id(info), safe=":/"), {"fields": FIELDS})
    if not d or not d.get("paperId"):
        return None
    pid = d["paperId"]
    for r in (d.get("references") or [])[:LIST_CAP] + (d.get("citations") or [])[:LIST_CAP]:
        if r:
            _stub(r, cache)
    cache["papers"][pid] = _node(d, slug)
    return pid


def fetch(slugs=None, limit=None, refresh=False, http=None, save=True, path=None, vault=None):
    cache = load_cache(path)
    vault = vault if vault is not None else vault_papers()
    todo = [s for s in (slugs or vault) if s in vault]
    fetched = skipped = missed = 0
    for s in todo:
        pid = cache["slugs"].get(s)
        if not refresh and ((pid and pid in cache["papers"] and cache["papers"][pid].get("slug"))
                            or s in cache["misses"]):
            skipped += 1
            continue
        if limit is not None and fetched + missed >= limit:
            break
        try:
            pid = fetch_one(cache, vault[s], s, http)
            reason = "not found on Semantic Scholar"
        except RuntimeError as e:
            pid, reason = None, f"error: {e}"
        if pid:
            cache["slugs"][s] = pid
            cache["misses"].pop(s, None)
            fetched += 1
            p = cache["papers"][pid]
            print(f"ok   {s}: {len(p['references'])} refs, {len(p['citations'])} cits", flush=True)
        else:
            if not reason.startswith("error"):
                cache["misses"][s] = reason
            missed += 1
            print(f"miss {s}: {reason}", flush=True)
        if save:
            save_cache(cache, path)
    print(f"fetched {fetched}, skipped {skipped}, missed {missed}", flush=True)
    return cache


# ---------------------------------------------------------------- pure graph functions

def vault_ids(cache):
    return {pid: s for s, pid in cache["slugs"].items() if pid in cache["papers"]}


def _refs(cache, pid):
    return set(cache["papers"].get(pid, {}).get("references", []))


def _cits(cache, pid):
    return set(cache["papers"].get(pid, {}).get("citations", []))


def coupling(cache, pid):
    """{vault paperId: shared references} (bibliographic coupling)."""
    mine = _refs(cache, pid)
    return {o: len(mine & _refs(cache, o)) for o in vault_ids(cache)
            if o != pid and mine & _refs(cache, o)}


def cocitation(cache, pid):
    """{vault paperId: papers citing both}."""
    mine = _cits(cache, pid)
    return {o: len(mine & _cits(cache, o)) for o in vault_ids(cache)
            if o != pid and mine & _cits(cache, o)}


def direct(cache, pid):
    """(out, in) vault paperId sets: cited by pid / citing pid (either side's data is used)."""
    vids = vault_ids(cache)
    refs, cits = _refs(cache, pid), _cits(cache, pid)
    out = {o for o in vids if o != pid and (o in refs or pid in _cits(cache, o))}
    inn = {o for o in vids if o != pid and (o in cits or pid in _refs(cache, o))}
    return out, inn


def resolve(cache, key):
    """slug | paperId | arXiv id -> paperId (or None)."""
    key = key.strip()
    if key in cache["slugs"]:
        return cache["slugs"][key]
    if key in cache["papers"]:
        return key
    k = re.sub(r"^(arxiv:|https?://arxiv\.org/abs/)", "", key, flags=re.I)
    for pid, p in cache["papers"].items():
        if p.get("arxiv") and p["arxiv"] == k:
            return pid
    return None


def rank_for(cache, pid, exclude=()):
    """[(slug, score, direct, coupling, cocitation)] best first; score = 2*direct + coupling + cocitation."""
    vids = vault_ids(cache)
    out, inn = direct(cache, pid)
    cp, cc = coupling(cache, pid), cocitation(cache, pid)
    rows = []
    for o in set(cp) | set(cc) | out | inn:
        d = (o in out) + (o in inn)
        rows.append((vids[o], 2 * d + cp.get(o, 0) + cc.get(o, 0), d, cp.get(o, 0), cc.get(o, 0)))
    rows = [r for r in rows if r[0] not in exclude]
    return sorted(rows, key=lambda r: (-r[1], r[0]))


def missing_for(cache, slugs=None):
    """[(count, paperId)] of non-vault papers cited by the most vault papers (restricted to `slugs`)."""
    vids = vault_ids(cache)
    wanted = None if slugs is None else set(slugs)
    cnt = Counter()
    for pid, s in vids.items():
        if wanted is not None and s not in wanted:
            continue
        for r in _refs(cache, pid):
            if r not in vids:
                cnt[r] += 1
    return sorted(((n, r) for r, n in cnt.items()), key=lambda t: (-t[0], t[1]))


def shortest_path(cache, a, b, any_node=False):
    """Directed BFS a->b along 'cites' edges. Returns [paperId, ...] or None."""
    vids = vault_ids(cache)
    if a == b:
        return [a]
    inc = {}   # edges known only from the cited side's `citations` list
    for pid, p in cache["papers"].items():
        for c in p.get("citations", []):
            inc.setdefault(c, set()).add(pid)

    def nxt(n):
        s = _refs(cache, n) | inc.get(n, set())
        return s if any_node else {x for x in s if x in vids}
    prev, q = {a: None}, deque([a])
    while q:
        n = q.popleft()
        for m in sorted(nxt(n)):
            if m in prev:
                continue
            prev[m] = n
            if m == b:
                path = [m]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                return path[::-1]
            q.append(m)
    return None


# ---------------------------------------------------------------- CLI

def _label(cache, pid):
    p = cache["papers"].get(pid, {})
    return p.get("slug") or f"{(p.get('title') or pid)[:70]} ({p.get('year') or '?'})"


def _need(cache, key, fetch_missing=False):
    pid = resolve(cache, key)
    if pid:
        return pid
    if not fetch_missing:
        sys.exit(f"{key!r} is not in the citation cache (run `fetch` first)")
    k = re.sub(r"^arxiv:", "", key, flags=re.I)
    pid = fetch_one(cache, {"arxiv": k})
    if not pid:
        sys.exit(f"Semantic Scholar does not know {key!r}")
    save_cache(cache)
    return pid


def cmd_neighbors(a):
    c = load_cache()
    pid = _need(c, a.key)
    out, inn = direct(c, pid)
    vids = vault_ids(c)
    print(_label(c, pid))
    print(f"cites ({len(out)}): " + ", ".join(sorted(vids[o] for o in out)))
    print(f"cited by ({len(inn)}): " + ", ".join(sorted(vids[o] for o in inn)))
    for title, d in (("coupling", coupling(c, pid)), ("co-citation", cocitation(c, pid))):
        print(f"{title}:")
        for o, n in sorted(d.items(), key=lambda t: (-t[1], vids[t[0]]))[:a.limit]:
            print(f"  {n:3d}  {vids[o]}")


def cmd_rank(a):
    c = load_cache()
    pid = _need(c, a.key, fetch_missing=True)
    vids = vault_ids(c)
    allrefs = c["papers"][pid]["references"]
    refs = [r for r in allrefs if r in vids]
    print(f"{_label(c, pid)}: {len(refs)}/{len(allrefs)} references are vault papers")
    for r in refs:
        print(f"  cites {vids[r]}")
    print("score  direct coupling cocit  slug")
    for s, sc, d, cp, cc in rank_for(c, pid)[:a.limit]:
        print(f"{sc:5d}  {d:6d} {cp:8d} {cc:5d}  {s}")


def scope_papers(scope):
    """Vault paper slugs inside a scope's projection (exit 2 on an unknown scope)."""
    from kb_distillery.core import scopes
    try:
        pages = scopes.scope_context(scope, ROOT)["pages"]
    except scopes.ScopeUnknown as exc:
        print("ERROR  " + str(exc), file=sys.stderr)
        sys.exit(2)
    return sorted(s for s in vault_papers() if s in pages)


def cmd_missing(a):
    c = load_cache()
    slugs = a.slugs or None
    if a.scope:
        slugs = scope_papers(a.scope)
        print("scope " + a.scope + ": " + str(len(slugs)) + " vault papers")
    for n, pid in missing_for(c, slugs)[:a.limit]:
        p = c["papers"].get(pid, {})
        print(f"{n:3d}  {p.get('title') or '?'} ({p.get('year') or '?'})  {pid}"
              + (f"  arXiv:{p['arxiv']}" if p.get("arxiv") else ""))


def cmd_path(a):
    c = load_cache()
    x, y = _need(c, a.a), _need(c, a.b)
    p = shortest_path(c, x, y, a.any)
    print(" -> ".join(_label(c, n) for n in p) if p else "none")


def cmd_status(a):
    c = load_cache()
    v = vault_papers()
    got = [s for s in v if c["slugs"].get(s) in c["papers"]]
    missed = [s for s in c["misses"] if s in v]
    print(f"cache {cache_path()}: {len(c['papers'])} papers, fetched_at {c['fetched_at']}")
    print(f"vault papers with an id: {len(v)}; covered {len(got)}; missed {len(missed)}; "
          f"not yet fetched {len(v) - len(got) - len(missed)}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kb_distillery.search.citations")
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("fetch")
    f.add_argument("--slug", action="append")
    f.add_argument("--limit", type=int)
    f.add_argument("--refresh", action="store_true")
    f.add_argument("--scope", help="fetch only the vault papers inside this scope's projection")
    for name in ("neighbors", "rank"):
        p = sp.add_parser(name)
        p.add_argument("key")
        p.add_argument("--limit", type=int, default=10)
    m = sp.add_parser("missing")
    m.add_argument("--slugs", nargs="*")
    m.add_argument("--limit", type=int, default=20)
    m.add_argument("--scope", help="only papers inside this scope's projection (scope-x)")
    pa = sp.add_parser("path")
    pa.add_argument("a")
    pa.add_argument("b")
    pa.add_argument("--any", action="store_true")
    sp.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        slugs = a.slug
        if a.scope:
            slugs = [s for s in scope_papers(a.scope) if not a.slug or s in a.slug]
            if not slugs:      # an empty list would mean "the whole vault" to fetch()
                print("scope " + a.scope + ": no vault papers to fetch")
                return
        fetch(slugs, a.limit, a.refresh)
    else:
        {"neighbors": cmd_neighbors, "rank": cmd_rank, "missing": cmd_missing,
         "path": cmd_path, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
