"""Typed relations between pages: the ones a page states and the ones computed from data the vault already has.

A page states relations in a frontmatter block (YAML, read with `yaml.safe_load` on that block only; the rest
of the frontmatter stays with the flat parser `kb_distillery.lint.lint.parse_frontmatter`, which skips the indented lines):

    relations:
      - to: implicit-bias-of-gradient-descent
        kind: extends
        note: the margin argument carries over to deep linear nets

A stored kind is legal when the knowledge base declares it in `kb.toml` `[edges] types` (read by
`kb_distillery.graph.model.edge_config`, with `symmetric` and `note_required`); anything else is dropped and reported
by `problems`. Computed kinds come from existing data:

    mentions           a wikilink or `related:` entry (the snapshot's `links`)
    shares-source      two concepts that cite a common source (the snapshot's `concept_links`)
    advisor-of / student-of   person pages' `advisors:` / `students:` slugs
    name-match         a source whose `authors:` names a person page, when neither page links the other
    collaborates-with  two person pages named together on one source's `authors:`
    similar-to         the closest pages by card vector (`<kb>/.cache/vectors.sqlite`), only when it exists

Every edge is keyed (source, target, kind) and carries `origin` (stored | computed), `note` and `weight`; a stored
edge wins over a computed one with the same key. Symmetric computed kinds are emitted once (source < target).
"""
import json
import os
import re
import unicodedata

from kb_distillery.vault.links import page_slug

STORED, COMPUTED, PROPOSED = "stored", "computed", "proposed"
PROPOSALS_FILE = "relations-proposals.jsonl"      # `<kb>/.cache/`, written by kb_distillery.graph.propose (every valid proposal)
MENTIONS, SHARES_SOURCE, NAME_MATCH = "mentions", "shares-source", "name-match"
ADVISOR_OF, STUDENT_OF, COLLABORATES_WITH, SIMILAR_TO = "advisor-of", "student-of", "collaborates-with", "similar-to"
COMPUTED_KINDS = (MENTIONS, SHARES_SOURCE, ADVISOR_OF, STUDENT_OF, NAME_MATCH, COLLABORATES_WITH, SIMILAR_TO)
SIMILAR_K = 3            # each page's closest pages …
SIMILAR_MIN = 0.75       # … at or above this cosine (thesis cards: ~200 pairs)

_LINK = re.compile(r"^\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]$")


def kind_name(kind):
    """`Open Problem In` / `open_problem_in` → `open-problem-in` (the spelling in pages and kb.toml)."""
    return re.sub(r"[\s_]+", "-", str(kind or "").strip().lower())


def edge_label(kind):
    """The Cypher edge label of a kind: `open-problem-in` → `OPEN_PROBLEM_IN`."""
    return re.sub(r"[^A-Z0-9]+", "_", str(kind or "").strip().upper()).strip("_")


# ---- the frontmatter block ------------------------------------------------------------------------------

def _frontmatter(text):
    if not (text or "").startswith("---"):
        return None
    end = text.find("\n---", 3)
    return None if end == -1 else text[3:end]


def relations_block(text):
    """The `relations:` key and its indented (or `- `) lines from the frontmatter, or None."""
    fm = _frontmatter(text)
    if fm is None:
        return None
    lines, out = fm.splitlines(), None
    for line in lines:
        if out is None:
            if re.match(r"^relations\s*:", line):
                out = [line]
            continue
        if line.strip() and not line.startswith((" ", "\t", "-")):
            break                                         # the next top-level key ends the block
        out.append(line)
    return "\n".join(out) if out else None


def _target(value):
    s = str(value or "").strip()
    m = _LINK.match(s)
    if m:
        return m.group(1).strip()
    return (page_slug(s) or s).strip()          # a bare slug, or a page path `slug.md`


def parse_relations(text):
    """[{to, kind, note}] stated on a page; [] when there is none or the block is not valid YAML."""
    block = relations_block(text)
    if not block:
        return []
    import yaml          # only pages with a block need it; kb_distillery.graph.query imports this module

    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError:
        return []
    items = data.get("relations") if isinstance(data, dict) else None
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        to, kind = _target(item.get("to")), kind_name(item.get("kind"))
        if to and kind:
            note = item.get("note")
            out.append({"to": to, "kind": kind, "note": str(note).strip() if note is not None else ""})
    return out


def format_relations(rels):
    """The frontmatter block for [{to, kind, note}] (what `parse_relations` reads back)."""
    lines = ["relations:"] if rels else []
    for r in rels or ():
        lines += [f"  - to: {r['to']}", f"    kind: {r['kind']}"]
        if r.get("note"):
            lines.append(f"    note: {json.dumps(r['note'], ensure_ascii=False)}")   # JSON strings are YAML
    return "\n".join(lines)


def set_relations(text, rels):
    """`text` with its frontmatter `relations:` block replaced by `rels`, or added after the last frontmatter key
    when the page had none. Nothing else in the page changes. Raises ValueError when there is no frontmatter."""
    end = text.find("\n---", 3) if text.startswith("---") else -1
    if end == -1:
        raise ValueError("page has no frontmatter")
    new = format_relations(rels)
    block = relations_block(text)
    if block:
        return text.replace(block.rstrip("\n"), new, 1)
    return text[:end] + "\n" + new + text[end:]


# ---- stored edges ---------------------------------------------------------------------------------------

def _check(slug, rel, pages, config):
    kinds = set(config.get("types") or ())
    if rel["kind"] not in kinds:
        return f"{slug}: relation kind `{rel['kind']}` is not declared in kb.toml [edges] types"
    if rel["to"] not in pages:
        return f"{slug}: relation `{rel['kind']}` points to a missing page `{rel['to']}`"
    if rel["to"] == slug:
        return f"{slug}: relation `{rel['kind']}` points to the page itself"
    if rel["kind"] in set(config.get("note_required") or ()) and not rel["note"]:
        return f"{slug}: relation `{rel['kind']}` → `{rel['to']}` needs a note"
    return None


def stored_edges(pages, config):
    """Edges the pages state that the knowledge base accepts. A symmetric kind is stored once (source < target),
    so a pair that states it from both pages is one edge; the first page (by slug) keeps its note."""
    symmetric = set(config.get("symmetric") or ())
    out = []
    for slug, (_rel, _fm, text) in sorted(pages.items()):
        for r in parse_relations(text):
            if _check(slug, r, pages, config) is None:
                a, b = _pair(slug, r["to"]) if r["kind"] in symmetric else (slug, r["to"])
                out.append(_edge(a, b, r["kind"], STORED, r["note"], 1.0))
    return out


def problems(pages, config):
    """One line per stated relation that `stored_edges` drops (unknown kind, missing page, missing note)."""
    out = []
    for slug, (_rel, _fm, text) in sorted(pages.items()):
        out += [p for p in (_check(slug, r, pages, config) for r in parse_relations(text)) if p]
    return out


# ---- computed edges -------------------------------------------------------------------------------------

def _edge(source, target, kind, origin, note="", weight=1.0):
    return {"source": source, "target": target, "kind": kind, "origin": origin, "note": note, "weight": weight}


def _pair(a, b):
    return (a, b) if a < b else (b, a)


def _slugs(value):
    vals = value if isinstance(value, list) else [value] if value else []
    return [s for s in (_target(v) for v in vals) if s and s not in ("none", "unknown")]


def _norm_name(name):
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s.lower())).strip()


def _aliases(root):
    path = os.path.join(root, "meta", "aliases.tsv") if root else ""
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or "\t" not in line:
                continue
            mention, slug = line.rstrip("\n").split("\t", 1)
            if mention.strip() and slug.strip():
                out[_norm_name(mention)] = slug.strip()
    return out


def person_names(pages, titles, root=None):
    """{normalised name: person slug} from person pages' slugs and titles plus meta/aliases.tsv."""
    persons = {s for s, (_r, fm, _t) in pages.items() if fm.get("type") == "person"}
    names = {}
    for s in sorted(persons):
        for n in (s.replace("-", " "), titles.get(s, "")):
            if _norm_name(n):
                names.setdefault(_norm_name(n), s)
    for mention, slug in _aliases(root).items():
        if slug in persons:
            names.setdefault(mention, slug)
    return names


def _authors(fm):
    a = fm.get("authors")
    return [x for x in (a if isinstance(a, list) else [a] if a else []) if str(x).strip()]


def person_edges(pages):
    """advisor-of / student-of from person pages' `advisors:` / `students:` (nothing when no page has them)."""
    out = []
    for slug, (_r, fm, _t) in sorted(pages.items()):
        if fm.get("type") != "person":
            continue
        for a in _slugs(fm.get("advisors")):
            if a in pages and a != slug:
                out += [_edge(slug, a, STUDENT_OF, COMPUTED), _edge(a, slug, ADVISOR_OF, COMPUTED)]
        for s in _slugs(fm.get("students")):
            if s in pages and s != slug:
                out += [_edge(slug, s, ADVISOR_OF, COMPUTED), _edge(s, slug, STUDENT_OF, COMPUTED)]
    return out


def author_edges(pages, names, mentioned, layer_of):
    """name-match (source → person named in its authors, unless the pair already mentions) and
    collaborates-with (person pairs named on one source, weight = shared sources)."""
    out, together = [], {}
    for slug, (_r, fm, _t) in sorted(pages.items()):
        if layer_of.get(fm.get("type", "")) != "source" and fm.get("layer") != "source":
            continue
        found = sorted({names[n] for n in (_norm_name(a) for a in _authors(fm)) if n in names} - {slug})
        for p in found:
            if _pair(slug, p) not in mentioned:
                out.append(_edge(slug, p, NAME_MATCH, COMPUTED, "named in authors"))
        for i, a in enumerate(found):
            for b in found[i + 1:]:
                together[(a, b)] = together.get((a, b), 0) + 1
    for (a, b), n in sorted(together.items()):
        out.append(_edge(a, b, COLLABORATES_WITH, COMPUTED, f"{n} shared source{'s' if n != 1 else ''}", float(n)))
    return out


_VEC_CACHE = {}          # db path → (mtime_ns, Vectors)


def _vectors(root):
    path = os.path.join(root, ".cache", "vectors.sqlite") if root else ""
    if not path or not os.path.exists(path):
        return None
    from kb_distillery.search import vectors

    mtime = os.stat(path).st_mtime_ns
    hit = _VEC_CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        v = vectors.load(path)
    except Exception:  # noqa: BLE001 — an unreadable store means no similar-to, never a 500
        v = None
    _VEC_CACHE[path] = (mtime, v)
    return v


def similar_edges(pages, root, k=SIMILAR_K, min_cos=SIMILAR_MIN):
    """similar-to between each page and its k closest pages at or above `min_cos`; [] without a vector store."""
    import numpy as np

    v = _vectors(root)
    if v is None or len(v) < 2:
        return []
    store = os.path.join(root, ".cache", "vectors.sqlite")
    key = (store, _VEC_CACHE.get(store, (0,))[0], frozenset(pages), k, min_cos)
    if _SIM_CACHE.get("key") == key:
        return [dict(e) for e in _SIM_CACHE["edges"]]
    keep = [i for i, s in enumerate(v.slugs) if s in pages and np.all(np.isfinite(v.m[i]))]
    edges = []
    if len(keep) >= 2:
        m = v.m[keep].astype(np.float32)
        slugs = [v.slugs[i] for i in keep]
        best = {}
        for start in range(0, len(slugs), 512):          # row blocks: never the whole n×n matrix at once
            with np.errstate(all="ignore"):
                block = np.nan_to_num(m[start:start + 512] @ m.T, nan=-1.0, posinf=-1.0, neginf=-1.0)
            for r in range(block.shape[0]):
                block[r, start + r] = -1.0
            kk = min(k, block.shape[1] - 1)
            top = np.argpartition(-block, kk, axis=1)[:, :kk] if kk > 0 else np.zeros((block.shape[0], 0), int)
            for r, row in enumerate(top):
                for j in row:
                    c = float(block[r, j])
                    if c >= min_cos:
                        best[_pair(slugs[start + r], slugs[int(j)])] = round(c, 3)
        edges = [_edge(a, b, SIMILAR_TO, COMPUTED, f"cosine {c:.2f}", c) for (a, b), c in sorted(best.items())]
    _SIM_CACHE.update(key=key, edges=edges)
    return [dict(e) for e in edges]


_SIM_CACHE = {}          # one entry: (store, its mtime, page set, k, min) → edges


def build(pages, nodes, links, concept_links, config, root=None):
    """Every relation of a knowledge base, stored first, deduplicated on (source, target, kind)."""
    titles = {n["id"]: n.get("title", "") for n in nodes}
    layer_of = {n.get("type", ""): n.get("layer", "") for n in nodes}
    mentions = [_edge(l["source"], l["target"], MENTIONS, COMPUTED)
                for l in links if l.get("kind") in ("wikilink", "related")]
    mentioned = {_pair(e["source"], e["target"]) for e in mentions}
    shares = [_edge(c["source"], c["target"], SHARES_SOURCE, COMPUTED,
                    f"{c['shared']} shared source{'s' if c['shared'] != 1 else ''}", float(c["shared"]))
              for c in concept_links]
    groups = (stored_edges(pages, config), mentions, shares, person_edges(pages),
              author_edges(pages, person_names(pages, titles, root), mentioned, layer_of), similar_edges(pages, root))
    out, seen = [], set()
    for group in groups:
        for e in group:
            key = (e["source"], e["target"], e["kind"])
            if key not in seen:
                seen.add(key)
                out.append(e)
    return out


def read_proposals(root=None):
    """Every LLM relation proposal of a knowledge base: [{from, to, kind, note, confidence, run}], one per
    (from, to, kind), best confidence first. [] when it has none. Read-only; nothing here is knowledge."""
    from kb_distillery import paths
    path = os.path.join(root or paths.ROOT, ".cache", PROPOSALS_FILE)
    if not os.path.isfile(path):
        return []
    best = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                conf = float(r["confidence"])
                key = (r["from"], r["to"], kind_name(r["kind"]))
            except (ValueError, KeyError, TypeError):
                continue
            if key not in best or conf > best[key]["confidence"]:
                best[key] = {"from": key[0], "to": key[1], "kind": key[2], "note": str(r.get("note") or ""),
                             "confidence": conf, "run": str(r.get("run") or "")}
    return sorted(best.values(), key=lambda r: (-r["confidence"], r["from"], r["to"], r["kind"]))
