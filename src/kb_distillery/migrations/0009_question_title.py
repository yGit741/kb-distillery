"""Question pages (schema 1.1): a short H1 (≤ 80 chars) plus a required `## Question` section.

Mechanical part (idempotent): a question page without a `## Question` section gets one right after its
H1, holding the H1 text verbatim — the formal statement a short name later replaces. Nothing else moves;
the frontmatter and every other section are left byte-for-byte.
Editorial part (reported, never rewritten): H1s over the limit are listed so `ops migrate` prints the
worklist — shortening a title to the question's *name* is a human/LLM pass (skill wiki-edit).

    python src/kb_distillery/migrations/0009_question_title.py [--root R]
"""
import argparse
import os

PRODUCES = (1, 1)
TITLE_MAX = 80
HEADING = "## Question"


def _h1(text):
    return next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), "")


def report(root):
    """{'pages': n, 'long_title': [(slug, len)], 'missing_question': [slug]} over wiki/q-*.md."""
    wiki = os.path.join(root, "wiki")
    out = {"pages": 0, "long_title": [], "missing_question": []}
    for name in sorted(os.listdir(wiki)) if os.path.isdir(wiki) else []:
        if not (name.startswith("q-") and name.endswith(".md")):
            continue
        with open(os.path.join(wiki, name), encoding="utf-8") as f:
            text = f.read()
        if "\ntype: question" not in text:
            continue
        slug = name[:-3]
        out["pages"] += 1
        n = len(_h1(text))
        if n > TITLE_MAX:
            out["long_title"].append((slug, n))
        if not any(l.strip() == HEADING for l in text.splitlines()):
            out["missing_question"].append(slug)
    return out


def insert_question(text):
    """`## Question\n\n<H1>\n` right after the H1 line (and its blank lines); unchanged when present."""
    if any(l.strip() == HEADING for l in text.splitlines()):
        return text
    lines = text.split("\n")
    i = next((k for k, l in enumerate(lines) if l.startswith("# ")), None)
    if i is None:
        return text
    h1 = lines[i][2:].strip()
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    return "\n".join(lines[:i + 1] + ["", HEADING, "", h1, ""] + lines[j:])


def apply(root):
    r = report(root)
    wiki = os.path.join(root, "wiki")
    for slug in r["missing_question"]:
        path = os.path.join(wiki, slug + ".md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(insert_question(text))
    print(f"question pages: {r['pages']} · `{HEADING}` inserted: {len(r['missing_question'])} · "
          f"H1 > {TITLE_MAX} chars (not rewritten): {len(r['long_title'])}")
    for slug in r["missing_question"]:
        print(f"  inserted {HEADING}  {slug}")
    for slug, n in r["long_title"]:
        print(f"  long title ({n})  {slug}")
    if r["long_title"]:
        print("titles are not rewritten — shorten each H1 to the question's name in a wiki-edit pass "
              "(skill wiki-edit); lint errors until then")
    return r


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=os.getcwd())
    apply(p.parse_args().root)
