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
