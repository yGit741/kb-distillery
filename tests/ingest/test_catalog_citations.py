"""Every cataloged paper gets its citations fetched, and the catalog step survives a fetch failure."""
from kb_distillery.ingest import catalog
from kb_distillery.search import citations


def test_fetch_citations_calls_fetch_for_the_slug(monkeypatch):
    monkeypatch.setenv(catalog.CITATIONS_ENV, "1")
    seen = []
    monkeypatch.setattr(citations, "fetch", lambda slugs=None, **_: seen.append(slugs))
    catalog.fetch_citations("paper-2020-x")
    assert seen == [["paper-2020-x"]]


def test_fetch_citations_never_raises(monkeypatch, capsys):
    monkeypatch.setenv(catalog.CITATIONS_ENV, "1")

    def boom(**_):
        raise OSError("offline")
    monkeypatch.setattr(citations, "fetch", boom)
    catalog.fetch_citations("paper-2020-x")
    assert "skipped for paper-2020-x" in capsys.readouterr().out


def test_fetch_citations_off_by_env(monkeypatch):
    monkeypatch.setenv(catalog.CITATIONS_ENV, "0")
    monkeypatch.setattr(citations, "fetch", lambda **_: (_ for _ in ()).throw(AssertionError("called")))
    catalog.fetch_citations("paper-2020-x")


def test_a_failed_fetch_stops_further_fetches(monkeypatch):
    monkeypatch.setenv(catalog.CITATIONS_ENV, "1")
    monkeypatch.setattr(catalog, "_CITATIONS_DOWN", [])
    calls = []

    def boom(slugs=None, **_):
        calls.append(slugs)
        raise OSError("HTTP 429")
    monkeypatch.setattr(citations, "fetch", boom)
    catalog.fetch_citations("paper-a")
    catalog.fetch_citations("paper-b")
    assert calls == [["paper-a"]]


def test_catalog_paper_fetches_citations(tmp_path, monkeypatch):
    for d in ("wiki", "raw/inbox", "raw/printed-docs"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "raw/inbox/x.pdf").write_bytes(b"%PDF-1.4 x")
    (tmp_path / "raw/inbox/.keep").write_text("")
    seen = []
    monkeypatch.setattr(catalog, "ROOT", str(tmp_path))
    monkeypatch.setattr(catalog, "_run_lint", lambda: None)
    monkeypatch.setattr(catalog, "set_collection", lambda *a: None)
    monkeypatch.setattr("kb_distillery.ingest.scrap.ROOT", str(tmp_path))
    monkeypatch.setattr(catalog, "fetch_citations", seen.append)
    _dest, slug = catalog.catalog_paper("raw/inbox/x.pdf", title="X Paper", year="2020")
    assert seen == [slug]
