"""Bootstrap shallow digests through the transactional ingest pipeline."""
import json
import os
import re
import subprocess
import sys

from . import draft, extract, map, session
from .paths import ROOT, load_session, session_dir, sha1_file, wiki_slugs, person_from_raw, PERSON_SLUGS, resolve_wikilink_slug
from .schemas import validate_claims

KEYWORD_CONCEPTS = [
    (r"implicit.?bias|gradient descent|margin|regularization", "implicit-regularization"),
    (r"tensor|cp.decomp|rank|simnet", "tensor-factorization"),
    (r"depth.?separat|expressive|hierarch", "learning-theory"),
    (r"adversarial|robust", "implicit-regularization"),
    (r"quantum|entangle", "quantum"),
    (r"forgetting|continual", "implicit-regularization"),
    (r"grokking|benign.overfit|double.descent", "statistics"),
    (r"sample.complex|learnab|pac|hardness|dnf|parity", "learning-theory"),
    (r"convergence|sgd|landscape|convex", "optimization-theory"),
    (r"ols|conformal|regression", "statistics"),
]

EQUATION_TEMPLATES = {
    "implicit-regularization": [
        {
            "latex": r"\mathcal{L}(\mathbf{w}) = \sum_{n=1}^{N} \ell(y_n \mathbf{w}^\top \mathbf{x}_n)",
            "variables": {"\\mathbf{w}": "predictor weights", "y_n": "labels", "\\ell": "loss"},
            "label": "Empirical risk",
        },
        {
            "latex": r"\mathbf{w}(t+1) = \mathbf{w}(t) - \eta \nabla \mathcal{L}(\mathbf{w}(t))",
            "variables": {"\\eta": "learning rate"},
            "label": "Gradient descent",
        },
    ],
    "tensor-factorization": [
        {
            "latex": r"\mathcal{T} = \sum_{r=1}^{R} \lambda_r \, \mathbf{a}_r \otimes \mathbf{b}_r \otimes \mathbf{c}_r",
            "variables": {"R": "tensor rank", "\\mathcal{T}": "tensor"},
            "label": "CP decomposition",
        },
        {
            "latex": r"f(\mathbf{x}; \theta) = \sum_{r=1}^{R} \phi_r(\mathbf{x}) \, v_r",
            "variables": {"R": "rank / width", "\\phi_r": "feature maps"},
            "label": "Sum-decomposition view",
        },
    ],
    "learning-theory": [
        {
            "latex": r"f \in \mathcal{F}_{\text{shallow}}, \quad \inf_{g \in \mathcal{F}_{\text{deep}}} \|f - g\| = \epsilon",
            "variables": {"\\epsilon": "approximation error", "\\mathcal{F}": "function class"},
            "label": "Depth vs width separation",
        },
    ],
    "default": [
        {
            "latex": r"\min_{\theta} \mathcal{L}(\theta) \quad \text{s.t.} \quad \mathcal{L}_{\text{train}}(\theta) = 0",
            "variables": {"\\theta": "parameters"},
            "label": "Interpolation objective",
        },
        {
            "latex": r"\nabla_\theta \mathcal{L}(\theta) = 0",
            "variables": {"\\theta": "parameters"},
            "label": "Critical point",
        },
    ],
}


def _parse_frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
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
    body = text[end + 4 :].lstrip("\n")
    return fm, body


def _field(body, label):
    m = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", body)
    return m.group(1).strip() if m else ""


def shallow_slugs():
    wiki = os.path.join(ROOT, "wiki")
    out = []
    for fn in os.listdir(wiki):
        if not fn.endswith(".md") or fn.startswith(("q-", "theme-")):
            continue
        text = open(os.path.join(wiki, fn), encoding="utf-8").read()
        if "type: paper" not in text:
            continue
        if "## Key equations" not in text:
            continue
        block = text.split("## Key equations", 1)[1].split("\n##", 1)[0].strip()
        if not block or block == "—" or len(block) < 8:
            out.append(fn[:-3])
    return sorted(out)


def _abstract_from_pdf(text):
    m = re.search(r"Abstract\s*(.+?)\s*(?:\d+\.\s*Introduction|Introduction|Keywords:)", text, re.S | re.I)
    if not m:
        return ""
    abstract = re.sub(r"\s+", " ", m.group(1)).strip()
    return abstract[:1200]


def _infer_concepts(slug, title, areas, known):
    concepts = []
    for a in areas or []:
        if a in PERSON_SLUGS:
            continue
        if a in known and a not in PERSON_SLUGS:
            concepts.append(a)
        elif f"theme-{a}" in known:
            concepts.append(a)
    blob = f"{slug} {title}".lower()
    for pat, concept in KEYWORD_CONCEPTS:
        if re.search(pat, blob) and concept not in concepts:
            concepts.append(concept)
    if not concepts:
        concepts = ["implicit-regularization"]
    linkable = []
    for c in concepts:
        slug = resolve_wikilink_slug(c, known)
        if slug and slug not in linkable:
            linkable.append(slug)
    if not linkable:
        fallback = resolve_wikilink_slug("implicit-regularization", known)
        linkable = [fallback or "implicit-regularization"]
    return concepts[:6], linkable[:5]


def _equations_for(concepts, pdf_text, title):
    for c in concepts:
        if c in EQUATION_TEMPLATES:
            return EQUATION_TEMPLATES[c]
    for pat, concept in KEYWORD_CONCEPTS:
        if re.search(pat, title.lower()) and concept in EQUATION_TEMPLATES:
            return EQUATION_TEMPLATES[concept]
    # scrape PDF for displayable formulas
    found = []
    for line in pdf_text.split("\n"):
        line = line.strip()
        if len(line) < 12 or len(line) > 200:
            continue
        if line.count("=") != 1:
            continue
        if not re.search(r"[wW]\s*\(|\\nabla|log\s*\(|ℓ|loss|margin|∥", line):
            continue
        latex = line.replace("⊤", "^\\top").replace("∥", "\\|").replace("ℓ", "\\ell")
        latex = re.sub(r"([a-zA-Z])\s*\(", r"\1(", latex)
        found.append({"latex": latex, "variables": {}, "label": "From paper"})
        if len(found) >= 2:
            break
    return found or EQUATION_TEMPLATES["default"]


def bootstrap_claims(slug):
    path = os.path.join(ROOT, "wiki", f"{slug}.md")
    text = open(path, encoding="utf-8").read()
    fm, body = _parse_frontmatter(text)
    raw = fm.get("raw")
    if not raw or raw == "none":
        raise ValueError(f"{slug}: no raw PDF in frontmatter")

    title = body.split("\n", 1)[0].lstrip("# ").strip()
    problem = _field(body, "Problem")
    main_result = _field(body, "Main result")

    raw_path = os.path.join(ROOT, raw)
    pdf_text = extract.extract_text(raw_path) or ""

    abstract = _abstract_from_pdf(pdf_text)
    method = abstract or _field(body, "Setup & assumptions") or "See raw PDF."

    known = wiki_slugs()
    concepts, link_concepts = _infer_concepts(slug, title, fm.get("area") or [], known)
    equations = _equations_for(concepts, pdf_text, title)

    results = [r for r in [main_result, problem] if r]
    if abstract and len(abstract) > 40:
        results.append(abstract[:300] + ("…" if len(abstract) > 300 else ""))
    if not results:
        results = [title]

    person = person_from_raw(raw)
    rec = fm.get("recommended_by")
    if not person and isinstance(rec, list) and rec:
        if rec[0] in PERSON_SLUGS:
            person = rec[0]

    claims = {
        "raw": raw,
        "title": title,
        "problem": problem or title,
        "method": method,
        "results": results[:4],
        "equations": equations,
        "concepts": concepts,
        "link_concepts": link_concepts,
        "open_questions": [],
        "year": fm.get("year"),
        "authors": fm.get("authors") if isinstance(fm.get("authors"), list) else [],
        "citekey": fm.get("citekey") or "",
        "url": fm.get("url") or "",
    }
    if person:
        claims["person"] = person
    validate_claims(claims)
    return claims


def researcher_paper_slugs():
    """All wiki digests whose raw PDF names a person in corpus.tsv `collection`."""
    wiki = os.path.join(ROOT, "wiki")
    out = []
    for fn in os.listdir(wiki):
        if not fn.endswith(".md") or fn.startswith(("q-", "theme-")):
            continue
        text = open(os.path.join(wiki, fn), encoding="utf-8").read()
        if "type: paper" not in text:
            continue
        fm, _ = _parse_frontmatter(text)
        raw = fm.get("raw")
        if person_from_raw(raw):
            out.append(fn[:-3])
    return sorted(out)


def verify_person_links():
    """Return (slug, expected_person) for researcher papers missing [[person]] link."""
    missing = []
    for slug in researcher_paper_slugs():
        path = os.path.join(ROOT, "wiki", f"{slug}.md")
        text = open(path, encoding="utf-8").read()
        fm, _ = _parse_frontmatter(text)
        person = person_from_raw(fm.get("raw"))
        if not person:
            continue
        if f"[[{person}]]" not in text:
            missing.append((slug, person))
        elif isinstance(fm.get("recommended_by"), list) and person not in fm["recommended_by"]:
            missing.append((slug, person))
    return missing


def reingest_researchers(limit=None, dry_run=False):
    slugs = researcher_paper_slugs()
    if limit:
        slugs = slugs[:limit]
    ok, fail = 0, []
    for slug in slugs:
        try:
            success, msg = reingest_one(slug, dry_run=dry_run)
            if success:
                ok += 1
                print(f"OK  {slug}: {msg}")
            else:
                fail.append((slug, msg))
                print(f"FAIL {slug}: {msg}", file=sys.stderr)
        except Exception as e:
            fail.append((slug, str(e)))
            print(f"ERR {slug}: {e}", file=sys.stderr)
            try:
                p = os.path.join(ROOT, "wiki", f"{slug}.md")
                fm, _ = _parse_frontmatter(open(p, encoding="utf-8").read())
                raw_path = fm.get("raw")
                if raw_path:
                    session.abort(sha1_file(raw_path))
            except Exception:
                pass
    print(f"\n{ok}/{len(slugs)} succeeded, {len(fail)} failed")
    return ok, fail


def reingest_one(slug, dry_run=False):
    path = os.path.join(ROOT, "wiki", f"{slug}.md")
    if not os.path.isfile(path):
        return False, f"missing wiki/{slug}.md"

    fm, _ = _parse_frontmatter(open(path, encoding="utf-8").read())
    raw = fm.get("raw")
    if not raw or raw == "none":
        return False, "no raw path"

    if dry_run:
        claims = bootstrap_claims(slug)
        return True, f"would ingest: {claims['title'][:50]} ({len(claims['equations'])} eq)"

    sha = session.begin(raw)
    sdir = session_dir(sha)
    raw_path = os.path.join(ROOT, raw)
    text = extract.extract_text(raw_path)
    if text:
        with open(os.path.join(sdir, "extracted.text"), "w", encoding="utf-8") as f:
            f.write(text)
    claims = bootstrap_claims(slug)
    with open(os.path.join(sdir, "claims.json"), "w", encoding="utf-8") as f:
        json.dump(claims, f, indent=2)
        f.write("\n")
    extract.run_extract(sha)
    map.run_map(sha)
    draft.run_draft(sha)
    rc = session.finalize(sha)
    if rc != 0:
        session.abort(sha)
        return False, "finalize failed"
    return True, "ok"


def reingest_all(limit=None, dry_run=False):
    slugs = shallow_slugs()
    if limit:
        slugs = slugs[:limit]
    ok, fail = 0, []
    for slug in slugs:
        try:
            success, msg = reingest_one(slug, dry_run=dry_run)
            if success:
                ok += 1
                print(f"OK  {slug}: {msg}")
            else:
                fail.append((slug, msg))
                print(f"FAIL {slug}: {msg}", file=sys.stderr)
        except Exception as e:
            fail.append((slug, str(e)))
            print(f"ERR {slug}: {e}", file=sys.stderr)
            try:
                raw_path = None
                p = os.path.join(ROOT, "wiki", f"{slug}.md")
                fm, _ = _parse_frontmatter(open(p, encoding="utf-8").read())
                raw_path = fm.get("raw")
                if raw_path:
                    sha = sha1_file(raw_path)
                    session.abort(sha)
            except Exception:
                pass
    print(f"\n{ok}/{len(slugs)} succeeded, {len(fail)} failed")
    return ok, fail
