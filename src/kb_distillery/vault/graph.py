"""Wiki graph helpers — links, sections, token overlap (0 LLM)."""
import os
import re
from kb_distillery.config import pages as page_conventions
from kb_distillery.vault import links as page_links

TOKEN = re.compile(r"[a-z0-9]+")

NEGATION = frozenset({
    "not", "no", "never", "without", "fails", "fail", "cannot", "can't",
    "doesnt", "doesn't", "dont", "don't", "unlikely", "impossible",
})
SCOPE_WORDS = frozenset({
    "linear", "deep", "shallow", "finite", "infinite", "width", "depth",
    "overparameterized", "underparameterized", "real", "complex",
})

def sections_by_type():
    """The sections worth reading per page type; the takeaways heading is the kb's (kb_distillery.config.pages)."""
    takeaways = page_conventions.takeaways_heading()
    return {
    "paper": ["Problem", "Main result", "Setup & assumptions", takeaways,
              "Connections", "Links out"],
    "part": ["Problem", "Main result", "Setup & assumptions", takeaways,
             "Connections", "Links out"],
    "book": ["Overview", "Chapters", "Key concepts", "Threads"],
    "question": ["Question", "Why it matters", "Current state"],
    "idea": ["One-liner", "Intuition", "Formal", "Connections"],
    "topic": ["Scope", "Key concepts", "Threads", "Papers"],
    "course": ["Overview", "Contents", "Threads"],
    "series": ["Overview", "Contents", "Threads"],
    "notebook": ["Overview", "Chapters", "Threads"],
    }


def tokenize(text):
    return [t for t in TOKEN.findall((text or "").lower()) if len(t) > 1]


def extract_section(text, heading):
    marker = f"## {heading}"
    if marker not in text:
        return ""
    _, rest = text.split(marker, 1)
    lines = []
    for line in rest.splitlines()[1:]:
        if line.startswith("## "):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def claim_text(slug, fm, text):
    """Extract comparable claim snippets for coherence checks."""
    t = fm.get("type", "")
    parts = []
    if t in ("paper", "part"):
        body = text.split("\n---", 1)[-1] if text.startswith("---") else text
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("**Main result"):
                parts.append(s)
            if s.startswith("**Problem"):
                parts.append(s)
        for h in ("Problem", "Main result", "Setup & assumptions"):
            parts.append(extract_section(text, h))
    elif t == "question":
        parts.append(extract_section(text, "Question"))
        parts.append(extract_section(text, "Current state"))
    elif t == "idea":
        parts.append(extract_section(text, "One-liner"))
        parts.append(extract_section(text, "Formal"))
    else:
        parts.append(extract_section(text, "Scope"))
    blob = " ".join(p for p in parts if p).strip()
    return blob[:4000]


def outbound_links(text, fm=None):
    slugs = set(page_links.targets(text))
    if fm:
        slugs.update(page_links.refs(fm.get("related")))
    return slugs


def inbound_index(pages):
    idx = {slug: set() for slug in pages}
    for slug, (_rel, fm, text) in pages.items():
        for target in outbound_links(text, fm):
            if target in idx:
                idx[target].add(slug)
    return idx


def one_hop(seed, pages, inbound=None, cap=12):
    if seed not in pages:
        return []
    inbound = inbound or inbound_index(pages)
    _rel, fm, text = pages[seed]
    neighbors = set(outbound_links(text, fm))
    neighbors |= inbound.get(seed, set())
    neighbors.discard(seed)
    seed_claim = tokenize(claim_text(seed, fm, text))
    scored = []
    for n in neighbors:
        if n not in pages:
            continue
        _r, nfm, ntext = pages[n]
        overlap = len(set(seed_claim) & set(tokenize(claim_text(n, nfm, ntext))))
        scored.append((overlap, n))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [n for _s, n in scored[:cap]]


def jaccard(a, b):
    sa, sb = set(tokenize(a)), set(tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


NEG_WINDOW = 4
SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")
STOPWORDS = frozenset({
    "the", "and", "for", "are", "was", "were", "with", "that", "this", "from", "into", "than",
    "then", "its", "their", "has", "have", "had", "can", "may", "will", "all", "any", "but",
    "from", "over", "under", "via", "per", "such", "each", "when", "which", "while", "where",
    "also", "only", "very", "more", "most", "some", "being", "been", "does", "did", "our",
    "one", "two", "use", "uses", "used", "show", "shows", "go", "goes", "almost", "certain",
    "stub", "see", "paper", "main", "result", "problem", "setup",
})


def polarity_tokens(text):
    toks = set(tokenize(text))
    neg = toks & NEGATION
    scope = toks & SCOPE_WORDS
    content = toks - NEGATION - SCOPE_WORDS
    return content, neg, scope


def _content(tok, drop=frozenset()):
    return len(tok) > 2 and tok not in STOPWORDS and tok not in NEGATION and tok not in drop


def _sentences(text, drop=frozenset()):
    """Per sentence: (all content tokens, content tokens within NEG_WINDOW of a negation)."""
    out = []
    for sent in SENTENCE_SPLIT.split(text or ""):
        toks = tokenize(sent)
        if not toks:
            continue
        negs = [i for i, t in enumerate(toks) if t in NEGATION]
        near = set()
        for i in negs:
            for j in range(max(0, i - NEG_WINDOW), min(len(toks), i + NEG_WINDOW + 1)):
                if _content(toks[j], drop):
                    near.add(toks[j])
        out.append(({t for t in toks if _content(t, drop)}, near, bool(negs)))
    return out


def polarity_clash(text_a, text_b, ignore=()):
    """Purely lexical: one side negates a topic (negation within NEG_WINDOW tokens of >=2
    shared content tokens) that the other side asserts in a sentence with no negation.
    `ignore`: tokens that are the pages' own title words (slugs) — sharing those proves nothing."""
    drop = frozenset(ignore)
    sa, sb = _sentences(text_a, drop), _sentences(text_b, drop)
    best = 0
    for neg_side, aff_side in ((sa, sb), (sb, sa)):
        for _all, near, has_neg in neg_side:
            if not has_neg or len(near) < 2:
                continue
            for all_b, _near_b, neg_b in aff_side:
                if neg_b:
                    continue
                best = max(best, len(near & all_b))
    return best >= 2, best


def score_pair(slug_a, slug_b, pages):
    if slug_a not in pages or slug_b not in pages:
        return 0
    _ra, fma, ta = pages[slug_a]
    _rb, fmb, tb = pages[slug_b]
    ca, cb = claim_text(slug_a, fma, ta), claim_text(slug_b, fmb, tb)
    clash, shared = polarity_clash(ca, cb)
    overlap = len(set(tokenize(ca)) & set(tokenize(cb)))
    score = overlap + (20 if clash else 0)
    return score
