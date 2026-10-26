import os

import pytest

from kb.core import summary as S
from kb.summaries import pipeline as P

PAGE = """---
type: paper
layer: source
depth: easy
title: "A paper"
---

# A paper

**Problem:** Why do big nets generalize?

**Main result:** Norm-based bounds explain it.

## Key claims
- Claim one.

## Connections
[[x]] · [[y]]

## My notes
private thoughts

## Links out
- http://example.org
"""


def test_hash_ignores_connections_and_notes():
    h = S.summary_hash(PAGE)
    assert h == S.summary_hash(PAGE.replace("[[x]] · [[y]]", "[[z]]").replace("private", "other"))
    assert h == S.summary_hash(PAGE.replace("Claim one.", "Claim   one."))     # whitespace only
    assert h != S.summary_hash(PAGE.replace("Claim one.", "Claim two."))
    assert h != S.summary_hash(PAGE.replace("Norm-based", "Margin-based"))


def test_problems():
    good = "A paper showing that norm-based bounds, not parameter counts, explain why overparameterized nets generalize."
    assert S.problems(good) == []
    assert S.problems("short")
    assert S.problems(good + "\nx")
    assert S.problems(good + " #1")
    assert S.problems(good + ' "q"')
    assert S.problems(good + " שלום")
    assert S.problems("x" * 321)


@pytest.mark.parametrize("fm,need", [
    ({"type": "paper", "depth": "easy"}, True),
    ({"type": "paper", "depth": "listed"}, False),
    ({"type": "idea", "layer": "concept"}, True),
    ({"type": "course", "layer": "collection"}, False),
    ({"type": "series", "layer": "collection"}, True),
])
def test_needs_summary(fm, need):
    assert S.needs_summary(fm) is need


def test_page_input_drops_private_sections():
    page = {"slug": "a", "fm": {"type": "paper", "depth": "easy", "title": '"A paper"'}, "text": PAGE}
    s = P.page_input(page)
    assert "private thoughts" not in s and "example.org" not in s
    assert "Claim one." in s and "Title: A paper" in s


def test_set_fields_replaces_and_appends():
    t = P.set_fields(PAGE, {"summary": '"one"', "summary_from": "abc"})
    t = P.set_fields(t, {"summary": '"two"'})
    fm = t.split("\n---", 1)[0]
    assert fm.count("summary:") == 1 and 'summary: "two"' in fm and "summary_from: abc" in fm
    assert t.endswith(PAGE.split("\n---", 1)[1])


def test_status_and_sample(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    for i in range(12):
        (wiki / f"p{i}.md").write_text(PAGE)
    (wiki / "idea.md").write_text("---\ntype: idea\nlayer: concept\n---\n\n# An idea\n")
    (wiki / "heb.md").write_text(PAGE.replace("# A paper", "# שלום").replace('title: "A paper"', 'title: "שלום"'))
    (wiki / "mine.md").write_text(PAGE.replace("depth: easy", 'depth: easy\nsummary: "x"\nsummary_by: me'))
    pages = P.load_pages(str(tmp_path))
    st = {p["slug"]: P.status(p) for p in pages}
    assert st["mine"] == "mine" and st["idea"] == "missing"
    picked = P.sample(P.todo(pages), 5, hebrew_min=1)
    slugs = [p["slug"] for p in picked]
    assert len(slugs) == 5 and "heb" in slugs and "idea" in slugs   # Hebrew seat + small cell gets a seat


def test_propose_validates_and_retries(monkeypatch):
    pages = [{"slug": s, "fm": {"type": "idea"}, "text": PAGE} for s in ("a", "b")]
    good = "An idea page arguing that norm-based capacity bounds, not raw parameter counts, explain generalization in big nets."
    calls = []

    def fake_ask(prompt, model, **kw):
        calls.append(prompt)
        if len(calls) == 1:
            return '{"a": "%s", "b": "too short"}' % good, 0.02, None
        return '{"b": "%s"}' % good.replace("An idea", "Another idea"), 0.01, None

    monkeypatch.setattr(P, "ask", fake_ask)
    rows = P.propose(pages, workers=1, log=lambda *_: None)
    assert [r["problems"] for r in rows] == [[], []]
    assert rows[1]["summary"].startswith("Another idea") and len(calls) == 2


def test_apply_refuses_before_schema(monkeypatch):
    monkeypatch.setattr(P.schema, "SCHEMA_VERSION", (1, 2))
    with pytest.raises(SystemExit):
        P.apply()


def test_apply_writes_and_skips_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(P.schema, "SCHEMA_VERSION", (1, 3))
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "a.md").write_text(PAGE)
    (wiki / "b.md").write_text(PAGE)
    good = "A paper showing that norm-based bounds, not parameter counts, explain why overparameterized nets generalize."
    props = tmp_path / "p.jsonl"
    P.save([{"slug": "a", "summary": good, "problems": [], "summary_from": S.summary_hash(PAGE)},
            {"slug": "b", "summary": good, "problems": [], "summary_from": "stale0000000"}], str(props))
    assert P.apply(root=str(tmp_path), path=str(props)) == ["a"]
    text = (wiki / "a.md").read_text()
    assert f'summary: "{good}"' in text and P.status(P.load_pages(str(tmp_path))[0]) == "ok"
    assert os.path.getsize(wiki / "b.md") == len(PAGE.encode())
