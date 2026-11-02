"""Build graph touches and proposals from think human zone."""
import os
import re

from kb_distillery.vault import links
from .paths import ROOT, think_cite, wiki_slugs
from kb_distillery.vault.schema import is_page_file


THEME_KEYWORDS = [
    (r"implicit|margin|grokking|forgetting|regularization", "implicit-regularization"),
    (r"tensor|rank|simnet|cp.decomp|factorization", "tensor-factorization"),
    (r"entropy|mutual.info|compression|information.theory|mi\b", "info-theory"),
    (r"quantum|entangle|hilbert", "quantum"),
    (r"complex|phase|holomorphic", "complex-nn"),
    (r"pac|hardness|dnf|sample.complex|parity|learnab", "learning-theory"),
    (r"convergence|sgd|gradient.flow|landscape|convex", "optimization-theory"),
    (r"ols|bias.variance|double.descent|conformal|regression", "statistics"),
]


def _walk_wiki():
    base = os.path.join(ROOT, "wiki")
    for fn in os.listdir(base):
        if is_page_file(fn):
            rel = f"wiki/{fn}"
            text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            yield fn[:-3], rel, text


def build_plan(think_rel, human_text):
    known = wiki_slugs()
    touches = set()
    for target in links.targets(human_text):
        if target in known:
            touches.add(target)

    blob = human_text.lower()
    themes = []
    for pat, theme in THEME_KEYWORDS:
        if re.search(pat, blob) and theme not in themes:
            themes.append(theme)

    weak = []
    for theme in themes:
        moc = f"theme-{theme}"
        if moc not in known:
            weak.append(f"theme {theme} has no [[{moc}]] yet")

    proposals = []
    for theme in themes:
        moc_rel = f"wiki/theme-{theme}.md"
        if os.path.isfile(os.path.join(ROOT, moc_rel)):
            proposals.append({
                "target": moc_rel,
                "action": "append_threads",
                "text": f"- Thread from `{think_rel}` — review and refine",
                "rationale": f"Human zone mentions {theme} themes",
            })

    for qslug in sorted(touches):
        if qslug.startswith("q-"):
            proposals.append({
                "target": f"wiki/{qslug}.md",
                "action": "update_section",
                "section": "Current state",
                "text": f"- Active in `{think_rel}` deliberation",
                "rationale": "Think page links this question",
            })

    not_promoted = []
    if re.search(r"advisor|gut|feel|meeting", blob):
        not_promoted.append("Personal / advisor commentary — keep in think only unless you promote manually")

    return {
        "source": think_cite(think_rel),
        "touches": sorted(touches),
        "themes_detected": themes,
        "weak_links": weak,
        "proposals": proposals,
        "not_promoted": not_promoted,
    }
