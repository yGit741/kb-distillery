"""Fact citations: placeholders expand (checked, never written) and a cited fact that went away is reported."""
import re
import shutil

import pytest

from kb_distillery.codekb import cites
from kb_distillery.codekb.generic.graph import Graph


@pytest.fixture
def kb(built, tmp_path):
    root = tmp_path / "kb"
    (root / cites.CARD_DIR).mkdir(parents=True)
    (root / "wiki").mkdir()
    for card in (built.out / "cards").glob("*.md"):
        shutil.copy(card, root / cites.CARD_DIR / card.name)
    return root


def fact(kb, slug, needle):
    text = (kb / cites.CARD_DIR / f"{slug}.md").read_text(encoding="utf-8")
    return re.search(rf"^\| (F[0-9a-f]{{5}}) \|[^\n]*{re.escape(needle)}", text, re.M).group(1)


def page(kb, name, body):
    (kb / "wiki" / f"{name}.md").write_text(f"---\ntitle: {name}\n---\n\n{body}\n", encoding="utf-8")


def test_cite_check_shows_the_expansion_and_writes_nothing(kb, capsys):
    fid = fact(kb, "ir-core-py-pkg", "slugify")
    page(kb, "a", f"The slug helper lowercases. {{{{core-py-pkg:{fid}}}}}")
    before = (kb / "wiki" / "a.md").read_text(encoding="utf-8")
    assert cites.cite(kb, [], check=True) == 0
    out = capsys.readouterr().out
    assert "would change a" in out and f"(`{fid}` [" in out and ")[^ir-core-py-pkg]" in out and "footnote to add: [^ir-core-py-pkg]" in out
    assert "1 pages, 1 would change, 0 with errors" in out and (kb / "wiki" / "a.md").read_text(encoding="utf-8") == before


def test_cite_without_check_refuses_to_write(kb, capsys):
    page(kb, "a", "no placeholders")
    assert cites.cite(kb, [], check=False) == 2 and "writes nothing yet" in capsys.readouterr().out


def test_unknown_card_and_fact_are_errors(kb, capsys):
    page(kb, "a", "x {{nope:Fabcde}} y {{core-py-pkg:Fabcde}}")
    assert cites.cite(kb, [], check=True) == 1
    out = capsys.readouterr().out
    assert "unknown card" in out and "fact Fabcde not in ir-core-py-pkg" in out


def test_check_cites_passes_on_an_expanded_citation_and_fails_when_the_fact_is_gone(kb, capsys):
    fid = fact(kb, "ir-core-py-pkg", "slugify")
    url = re.search(rf"^\| {fid} \|[^\n]*\]\((https[^)]+)\)", (kb / cites.CARD_DIR / "ir-core-py-pkg.md").read_text(encoding="utf-8"), re.M).group(1)
    page(kb, "a", f"Claim (`{fid}` [{cites.anchor_label(url)}]({url}))[^ir-core-py-pkg]\n\n[^ir-core-py-pkg]: Code IR")
    assert cites.check_cites(kb) == 0
    capsys.readouterr()
    page(kb, "b", "Claim (`Fabcde` [x.py:1](https://github.com/octocat/core/blob/abc/x.py#L1))[^ir-core-py-pkg]")
    assert cites.check_cites(kb) == 1
    out = capsys.readouterr().out
    assert "fact Fabcde is gone from ir-core-py-pkg" in out


def test_refresh_re_points_a_link_from_an_older_export(kb, capsys):
    fid = fact(kb, "ir-core-py-pkg", "slugify")
    new = re.search(rf"^\| {fid} \|[^\n]*\]\((https[^)]+)\)", (kb / cites.CARD_DIR / "ir-core-py-pkg.md").read_text(encoding="utf-8"), re.M).group(1)
    old = re.sub(r"/blob/[0-9a-f]{40}/", "/blob/" + "0" * 40 + "/", new)
    page(kb, "a", f"Claim (`{fid}` [{cites.anchor_label(old)}]({old}))[^ir-core-py-pkg]")
    assert cites.check_cites(kb) == 0 and "from an older export" in capsys.readouterr().out
    assert cites.cite(kb, ["a"], check=True, refresh=True) == 0
    assert new in capsys.readouterr().out


def test_anchor_labels_for_both_hosts():
    assert cites.anchor_label("https://github.com/o/r/blob/" + "a" * 40 + "/src/x.py#L7-L9") == "x.py:7"
    assert cites.anchor_label("https://gitlab.example.com/g/r/-/blob/" + "a" * 40 + "/src/x.py#L7-9") == "x.py:7"
    assert cites.anchor_label("https://example.com/files/x.py") == "x.py"


def test_the_card_ids_in_the_page_come_from_the_graph(built):
    assert Graph.load(built.out).meta["repos"]["core"]["sha"] in (built.out / "cards" / "ir-core-py-pkg.md").read_text(encoding="utf-8")
