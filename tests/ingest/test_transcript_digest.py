"""Digest reads a PDF's checked transcript (flag parsed-pdf) and carries its `!` / `!!` marks into the claims."""
import json
import os

import pytest

from kb_distillery import llm
from kb_distillery.ingest import draft, extract, schemas
from kb_distillery.parse import store
from tests.parse import pdfs

L1 = "[!](mark:%s/p0001/1)"
L2 = "[!!](mark:%s/p0002/1)"


@pytest.fixture
def kb(tmp_path):
    """A kb folder with one PDF of three pages; pages 1 and 2 are in its parsed store, each with a mark and a crop."""
    root = tmp_path / "kb"
    (root / "raw" / "printed-docs").mkdir(parents=True)
    (root / "kb.toml").write_text("[kb]\nid = 'fixture'\n")
    raw = root / "raw" / "printed-docs" / "2020-book.pdf"
    raw.write_bytes(pdfs.build())
    sha = store.sha1_bytes(raw.read_bytes())
    proot = store.parsed_root(str(root))
    l1, l2 = L1 % sha[:12], L2 % sha[:12]
    store.write_transcript_page(proot, sha, 1, "Page one has $a = b$ %s here." % l1, [{"id": 1, "level": "!"}])
    store.write_transcript_page(proot, sha, 2, "Page two has\n\n$$c = d$$\n\n%s" % l2, [{"id": 1, "level": "!!"}])
    os.makedirs(os.path.join(proot, sha, "crops"))
    for name in ("p0001-1.png", "p0002-1.png"):
        with open(os.path.join(proot, sha, "crops", name), "wb") as f:
            f.write(b"\x89PNG\r\n")
    return {"root": root, "raw": str(raw), "sha": sha, "proot": proot, "l1": l1, "l2": l2}


@pytest.mark.flag("parsed-pdf", True)
def test_the_transcript_is_the_text_when_every_page_is_stored(kb):
    text = extract.extract_text(kb["raw"], pages=(1, 2))
    assert text.startswith("[transcript of pages 1-2, checked against the page images; 2 formula(s) carry")
    assert "$a = b$ " + kb["l1"] in text and text.index("Page one") < text.index("Page two")
    assert not extract.extract_text(kb["raw"], pages=(1, 3)).startswith("[transcript")      # page 3 is not stored: text layer
    assert not extract.extract_text(kb["raw"]).startswith("[transcript")                    # no manifest: text layer
    assert not extract.extract_text(kb["raw"], max_pages=2).startswith("[transcript")       # a preview is the text layer
    store.write_transcript_page(kb["proot"], kb["sha"], 3, "Page three.", [])
    store.write_manifest(kb["proot"], kb["sha"], "raw/printed-docs/2020-book.pdf", 3)
    assert "no formula" not in extract.extract_text(kb["raw"]) and "Page three." in extract.extract_text(kb["raw"])


@pytest.mark.flag("parsed-pdf", False)
def test_flag_off_reads_the_text_layer(kb):
    assert extract.transcript(kb["raw"], (1, 2)) is None
    assert not (extract.extract_text(kb["raw"], pages=(1, 2)) or "").startswith("[transcript")


@pytest.mark.flag("parsed-pdf", True)
def test_crops_of_marked_formulas_go_with_the_fill_double_marks_first(kb, tmp_path, monkeypatch):
    text = extract.extract_text(kb["raw"], pages=(1, 2))
    crops = extract.mark_crops(kb["raw"], text)
    assert [c[0] for c in crops] == [kb["l2"], kb["l1"]] and all(os.path.isfile(c[1]) for c in crops)
    assert extract.mark_crops(kb["raw"], text, limit=1) == crops[:1]
    prompt = extract.fill_prompt({"raw": "r"}, text, crops)
    assert "image 1 is " + kb["l2"] in prompt and "Never\ndrop a `[!!]` link" in prompt
    assert "Marks." not in extract.fill_prompt({"raw": "r"}, "plain text layer")
    seen = []

    def run(reqs, backend=None, **kw):
        seen.extend(reqs)
        good = {"raw": "r", "title": "T", "problem": "p", "method": "m", "results": ["x"], "concepts": [],
                "equations": [{"latex": "c = d", "mark": kb["l2"]}]}
        return [llm.Result(id=r.id, text=json.dumps(good)) for r in reqs]
    monkeypatch.setattr(llm, "run", run)
    assert extract.fill_claims({"raw": "r"}, text, str(tmp_path), crops=crops) == 0
    assert list(seen[0].images) == [c[1] for c in crops]


@pytest.mark.flag("parsed-pdf", True)
def test_a_book_part_without_its_transcript_is_refused_with_the_command(kb, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(extract, "load_session", lambda sha: {"raw": "raw/printed-docs/2020-book.pdf", "scope": {"pages": [2, 3], "label": "Ch. 2"}})
    monkeypatch.setattr(extract, "session_dir", lambda sha: str(tmp_path))
    monkeypatch.setattr("kb_distillery.config.paths.vault_root", lambda: str(kb["root"]))
    assert extract.run_extract("abc") == 1
    err = capsys.readouterr().err
    assert "distill parse transcribe raw/printed-docs/2020-book.pdf --pages 2-3" in err
    assert not os.path.exists(os.path.join(str(tmp_path), "extracted.text"))


@pytest.mark.flag("parsed-pdf", False)
def test_flag_off_leaves_a_book_part_template_as_it_was():
    t = extract._template("raw/printed-docs/2020-book.pdf", {"label": "Ch. 2", "pages": [2, 3], "notes": True})
    assert "exercises" not in t and "notes" not in t


@pytest.mark.flag("parsed-pdf", True)
def test_filled_claims_validate_without_a_transcript_and_a_stuck_page_says_so(kb, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(extract, "load_session", lambda sha: {"raw": "raw/printed-docs/2020-book.pdf", "scope": {"pages": [2, 3], "label": "Ch. 2"}})
    monkeypatch.setattr(extract, "session_dir", lambda sha: str(tmp_path))
    monkeypatch.setattr("kb_distillery.config.paths.vault_root", lambda: str(kb["root"]))
    store.write_page(kb["proot"], kb["sha"], 3, "x", [{"kind": "lost", "detail": "d"}])           # needs-human
    assert extract.run_extract("abc") == 1 and "need a human" in capsys.readouterr().err
    good = {"raw": "raw/printed-docs/2020-book.pdf", "title": "T", "problem": "p", "method": "m", "results": ["x"], "concepts": []}
    (tmp_path / "claims.json").write_text(json.dumps(good))
    assert extract.run_extract("abc") == 0                                                      # nothing to read: validate only
    assert extract.transcript_gap(str(tmp_path / "elsewhere.pdf"), (1, 2)) is None


@pytest.mark.flag("parsed-pdf", True)
def test_crops_that_cannot_be_sent_do_not_stop_the_fill(kb, tmp_path, monkeypatch, capsys):
    calls = []

    def run(reqs, backend=None, **kw):
        calls.append(reqs[0].images)
        if reqs[0].images:
            raise llm.LLMError("images need the claude provider")
        good = {"raw": "r", "title": "T", "problem": "p", "method": "m", "results": ["x"], "concepts": []}
        return [llm.Result(id=r.id, text=json.dumps(good)) for r in reqs]
    monkeypatch.setattr(llm, "run", run)
    text = extract.extract_text(kb["raw"], pages=(1, 2))
    assert extract.fill_claims({"raw": "r"}, text, str(tmp_path), crops=extract.mark_crops(kb["raw"], text)) == 0
    assert len(calls) == 2 and not calls[1] and "filling without them" in capsys.readouterr().err
    assert extract.mark_crops(kb["raw"], "$x$ [!](mark:ffffffffffff/p0001/1)") == []          # another file's mark


@pytest.mark.flag("parsed-pdf", True)
def test_a_book_part_template_asks_for_exercises_and_for_notes_only_on_request():
    t = extract._template("raw/printed-docs/2020-book.pdf", {"label": "Ch. 2", "pages": [2, 3]})
    assert t["exercises"] == [{"label": "", "statement": ""}] and "notes" not in t
    t = extract._template("raw/printed-docs/2020-book.pdf", {"label": "Ch. 2", "pages": [2, 3], "exercises": False, "notes": True})
    assert "exercises" not in t and t["notes"] == ""
    assert "exercises" not in extract._template("raw/printed-docs/2020-paper.pdf", {})


def test_an_equation_keeps_its_mark_and_exercises_get_their_own_section():
    link = "[!!](mark:0123456789ab/p0002/1)"
    block = draft._equations_block([{"latex": "a = b", "mark": link, "label": "Eq. 1"},
                                    {"latex": "x = " + "y + " * 30 + "z", "mark": link}, {"latex": "c = d"}])
    assert "$a = b$ " + link in block and "$$\n\n" + link in block and "$c = d$\n" in block
    ex = draft._exercises_block({"exercises": [{"label": "2.1", "statement": "Show $a=b$."}, {"label": "", "statement": ""}],
                                 "notes": "First proved in 1999."})
    assert ex.startswith("## Exercises\n\n**2.1.** Show $a=b$.\n") and "## Notes and references\n\nFirst proved" in ex
    assert draft._exercises_block({}) == ""
    both = {"exercises": [{"label": "2.1", "statement": "Show $a=b$."}], "notes": "First proved in 1999."}
    assert "Notes and references" not in draft._exercises_block(both, {"pages": [1, 2]})        # notes only with --notes
    assert "Notes and references" in draft._exercises_block(both, {"notes": True})
    assert draft._exercises_block(both, {"exercises": False}) == ""
    odd = draft._exercises_block({"exercises": [{"label": 3.36, "statement": "## Hint\nDo it."}], "notes": "## History\nOld.\n## Links out"})
    assert "**3.36.** Hint\nDo it." in odd and odd.count("## ") == 2 and "**History**" in odd and "**Links out**" in odd


def test_claims_validation_of_marks_exercises_and_notes():
    base = {"raw": "r", "title": "T", "problem": "p", "method": "m", "results": ["x"], "concepts": []}
    assert schemas.validate_claims({**base, "equations": [{"latex": "a", "mark": "[!](mark:0123456789ab/p0002/1)"}],
                                    "exercises": [{"label": "1", "statement": "s"}], "notes": "n"})
    for bad, why in (({"equations": [{"latex": "a", "mark": "see the crop"}]}, "mark link"),
                     ({"equations": [{"latex": "a [!](mark:0123456789ab/p0002/1)"}]}, "never inside"),
                     ({"exercises": [{"label": 3.36, "statement": "s"}]}, "exercises"),
                     ({"exercises": "none"}, "exercises"), ({"notes": ["x"]}, "notes")):
        with pytest.raises(ValueError, match=why):
            schemas.validate_claims({**base, **bad})


def test_exercise_and_notes_switches_reach_the_chapter_scope(monkeypatch):
    import argparse
    from kb_distillery.ingest import cli
    rows = [{"start": 2, "end": 3, "title": "Two", "id": "ch2"}]
    monkeypatch.setattr(cli, "_row_scope", lambda args: (None, 0))
    monkeypatch.setattr(cli.book_mod, "verify_for_scope", lambda p: p)
    monkeypatch.setattr(cli.book_mod, "gate", lambda *a, **k: (rows, None))
    monkeypatch.setattr(cli.book_mod, "hub_slug", lambda raw: "book-x")
    base = {"raw_path": "raw/printed-docs/x.pdf", "chapter": "2"}
    (plain,), _ = cli._scopes(argparse.Namespace(**base, exercises=True, notes=False))
    assert "exercises" not in plain and "notes" not in plain and plain["chapter"] == "ch2"
    (off,), _ = cli._scopes(argparse.Namespace(**base, exercises=False, notes=True))
    assert off["exercises"] is False and off["notes"] is True


def test_a_redone_chapter_keeps_its_page(monkeypatch):
    import argparse
    from kb_distillery.ingest import cli
    rows = [{"start": 2, "end": 3, "title": "Two", "id": "ch2", "slug": "part-x-ch2-old-name", "status": "full"}]
    seen = {}
    monkeypatch.setattr(cli, "_row_scope", lambda args: (None, 0))
    monkeypatch.setattr(cli.book_mod, "verify_for_scope", lambda p: p)
    monkeypatch.setattr(cli.book_mod, "gate", lambda *a, **k: (seen.update(k) or (rows, None)))
    monkeypatch.setattr(cli.book_mod, "hub_slug", lambda raw: "book-x")
    (sc,), _ = cli._scopes(argparse.Namespace(raw_path="raw/printed-docs/x.pdf", chapter="2", redo=True, exercises=True, notes=False))
    assert seen["redo"] is True and sc["slug"] == "part-x-ch2-old-name"
