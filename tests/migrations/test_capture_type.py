"""0016: own-thought articles (`author: me`) become `capture` pages; kb.toml `[types] order` learns the type."""
import importlib.util
import os

import pytest

HERE = os.path.dirname(__file__)
PATH = os.path.join(HERE, "..", "..", "src", "kb_distillery", "migrations", "0016_capture_type.py")
_spec = importlib.util.spec_from_file_location("mig0016", PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

CAPTURE = """---
type: article
layer: source
author: me
raw: raw/images/capture-2026-11-14-basis.webp
related: [basis.md]
---

# Capture: basis
"""
WEB = """---
type: article
layer: source
url: https://example.com/x
---

# A web article
"""
IDEA = """---
type: idea
layer: concept
sources: [{resource: article-capture-2026-11-14-basis.md}]
related: [article-capture-2026-11-14-basis.md, article-web.md]
---

# Basis

From my [capture](article-capture-2026-11-14-basis.md), see also [web](article-web.md).
"""
TOML = """[kb]
id = "k"

[types]
order = ["topic", "idea",
         "article"]

[graph]
order = ["x"]
"""
CORPUS = "# header\npath\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n" \
         "raw/images/capture-2026-11-14-basis.webp\tabc\timages\tsource\tarticle-capture-2026-11-14-basis\t\t\n"


@pytest.fixture
def kb(tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "meta").mkdir()
    (tmp_path / "wiki" / "article-capture-2026-11-14-basis.md").write_text(CAPTURE)
    (tmp_path / "wiki" / "article-web.md").write_text(WEB)
    (tmp_path / "wiki" / "basis.md").write_text(IDEA)
    (tmp_path / "kb.toml").write_text(TOML)
    (tmp_path / "meta" / "corpus.tsv").write_text(CORPUS)
    return tmp_path


def test_produces_1_6():
    assert mig.PRODUCES == (1, 6)


def test_own_articles_become_captures_and_links_follow(kb):
    out = mig.apply(str(kb))
    assert out["renamed"] == 1 and out["order"] is True
    wiki = kb / "wiki"
    assert not (wiki / "article-capture-2026-11-14-basis.md").exists()
    page = (wiki / "capture-2026-11-14-basis.md").read_text()
    assert "type: capture" in page and "aliases: [article-capture-2026-11-14-basis]" in page
    assert (wiki / "article-web.md").read_text() == WEB
    idea = (wiki / "basis.md").read_text()
    assert "article-capture" not in idea
    assert idea.count("capture-2026-11-14-basis.md") == 3 and "article-web.md" in idea
    assert "\tcapture-2026-11-14-basis\t" in (kb / "meta" / "corpus.tsv").read_text()


def test_order_is_extended_only_in_the_types_table(kb):
    mig.apply(str(kb))
    toml = (kb / "kb.toml").read_text()
    assert '"article", "capture"]' in toml and 'order = ["x"]' in toml


def test_idempotent(kb):
    mig.apply(str(kb))
    snap = {p.name: p.read_text() for p in (kb / "wiki").iterdir()}
    toml = (kb / "kb.toml").read_text()
    assert mig.apply(str(kb))["renamed"] == 0
    assert snap == {p.name: p.read_text() for p in (kb / "wiki").iterdir()}
    assert toml == (kb / "kb.toml").read_text()


def test_dry_run_writes_nothing(kb):
    before = (kb / "kb.toml").read_text()
    assert mig.apply(str(kb), dry_run=True)["dry_run"] is True
    assert (kb / "wiki" / "article-capture-2026-11-14-basis.md").exists()
    assert (kb / "kb.toml").read_text() == before


def test_order_with_a_comment_keeps_capture_out_of_it(kb):
    (kb / "kb.toml").write_text('[types]\norder = [\n  "topic", "idea",  # people later\n]\n')
    mig.apply(str(kb))
    toml = (kb / "kb.toml").read_text()
    assert '"idea", "capture",  # people later' in toml


def test_crlf_and_quoted_type_are_retyped(kb):
    page = kb / "wiki" / "article-capture-2026-11-14-basis.md"
    page.write_bytes(CAPTURE.replace("type: article", 'type: "article"').replace("\n", "\r\n").encode())
    mig.apply(str(kb))
    text = (kb / "wiki" / "capture-2026-11-14-basis.md").read_bytes().decode()
    assert "type: capture\r\n" in text and "article-capture-2026-11-14-basis]" in text


def test_an_interrupted_run_is_finished_by_the_next(kb):
    wiki = kb / "wiki"
    old = wiki / "article-capture-2026-11-14-basis.md"
    (wiki / "capture-2026-11-14-basis.md").write_text(mig._retype(old.read_text(), "article-capture-2026-11-14-basis"))
    old.unlink()                                   # died after the rename, before the relink
    mig.apply(str(kb))
    assert "article-capture" not in (wiki / "basis.md").read_text()
    assert "\tcapture-2026-11-14-basis\t" in (kb / "meta" / "corpus.tsv").read_text()


def test_two_pages_onto_one_slug_refuse_before_writing(kb):
    (kb / "wiki" / "article-2026-11-14-basis.md").write_text(CAPTURE)
    (kb / "wiki" / "article-capture-2026-11-14-basis.md").unlink()
    (kb / "wiki" / "article-capture-2026-11-14-basis.md").write_text(CAPTURE)
    (kb / "wiki" / "article-2026-11-14-basis.md").rename(kb / "wiki" / "article-capture-x.md")
    (kb / "wiki" / "article-x.md").write_text(CAPTURE)
    before = (kb / "kb.toml").read_text()
    with pytest.raises(RuntimeError, match="two pages"):
        mig.apply(str(kb))
    assert (kb / "kb.toml").read_text() == before
