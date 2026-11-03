"""Clean-install papercuts: equations are optional off the equation types, no PDF hint for text sources."""
import os

import pytest

from kb_distillery.ingest import schemas
from kb_distillery.ingest.sources.books import book
from kb_distillery.storage import pdf

BASE = {"raw": "raw/web/a.md", "title": "T", "problem": "p", "method": "m", "results": ["r"], "concepts": []}


def test_an_article_needs_no_equations():
    assert schemas.validate_claims(BASE, page_type="article")
    assert schemas.validate_claims({**BASE, "equations": []}, page_type="article")
    assert schemas.validate_claims(BASE)                      # type not known yet (extract, map)


def test_a_paper_still_needs_an_equation():
    for page_type in ("paper", "part", "lecture"):
        with pytest.raises(ValueError, match="equations must be non-empty"):
            schemas.validate_claims({**BASE, "equations": []}, page_type=page_type)
        with pytest.raises(ValueError, match="equations must be non-empty"):
            schemas.validate_claims(BASE, page_type=page_type)
        assert schemas.validate_claims({**BASE, "equations": [{"latex": "E=mc^2"}]}, page_type=page_type)


def test_a_malformed_equation_is_still_rejected():
    with pytest.raises(ValueError, match="latex"):
        schemas.validate_claims({**BASE, "equations": [{"label": "x"}]}, page_type="article")


def test_markdown_source_never_asks_for_the_pdf_library(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pdf, "available", lambda: False)
    md = tmp_path / "a.md"
    md.write_text("# hi\n")
    assert book.page_count(str(md)) == 0
    assert capsys.readouterr().err == ""


def test_missing_pdf_hint_fits_the_install(monkeypatch):
    monkeypatch.delenv("PIXI_PROJECT_ROOT", raising=False)
    monkeypatch.setattr("sys.prefix", "/venv")
    assert "pip install pypdfium2" in pdf.missing_msg()
    monkeypatch.setattr("sys.prefix", "/repo/.pixi/envs/default")
    assert "pixi install" in pdf.missing_msg()


def test_finalize_lint_wants_equations_on_a_paper_but_not_an_article():
    from kb_distillery.lint import lint
    lint.errors.clear()
    body = "# T\n\n## Key equations\n\n## Takeaways\n"
    for slug, t in (("article-a", "article"), ("paper-2024-b", "paper")):
        fm = {"type": t, "depth": "full", "maturity": "digested"}
        lint.check_ingest_strict({slug: (f"wiki/{slug}.md", fm, body)})
    try:
        assert any("paper-2024-b" in e and "empty Key equations" in e for e in lint.errors)
        assert not any("article-a" in e and "Key equations" in e for e in lint.errors)
    finally:
        lint.errors.clear()


def test_placeholder_latex_does_not_count_as_an_equation():
    for latex in (None, "", "—"):
        with pytest.raises(ValueError, match="non-empty"):
            schemas.validate_claims({**BASE, "equations": [{"latex": latex}]}, page_type="paper")
