"""qmd search: cards sync, a client that never raises, and the `related` group behind semantic-search."""
import os

import pytest

from kb_distillery.search import cards, qmd_client
from kb_distillery.services import pages as svc

GOOD = "An idea page arguing that norm-based capacity bounds, not raw parameter counts, explain generalization."


def _page(fm, title="A page"):
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in fm.items()) + f"---\n\n# {title}\n\nBody.\n"


def test_cards_sync_writes_changed_removes_gone(tmp_path):
    wiki, out = tmp_path / "wiki", tmp_path / "cards"
    wiki.mkdir()
    (wiki / "a.md").write_text(_page({"type": "idea", "description": f'"{GOOD}"'}, "Idea A"))
    (wiki / "b.md").write_text(_page({"type": "paper", "depth": "listed", "description": f'"{GOOD}"'}))
    (wiki / "c.md").write_text(_page({"type": "course", "description": f'"{GOOD}"'}))
    (wiki / "d.md").write_text(_page({"type": "idea"}))
    r = cards.build(str(wiki), str(out))
    assert r == {"written": 1, "removed": 0, "cards": 1}
    assert (out / "a.md").read_text() == f"# Idea A\n\n{GOOD}\n"
    mtime = os.path.getmtime(out / "a.md")
    assert cards.build(str(wiki), str(out))["written"] == 0 and os.path.getmtime(out / "a.md") == mtime
    (wiki / "a.md").unlink()
    assert cards.build(str(wiki), str(out)) == {"written": 0, "removed": 1, "cards": 0}


def test_client_returns_none_when_service_is_down(monkeypatch):
    monkeypatch.setattr(qmd_client, "BASE", "http://127.0.0.1:9")     # discard port: nothing listens
    assert qmd_client.search("noise stability", timeout=0.3) is None
    assert qmd_client.health(timeout=0.3) is None and qmd_client.refresh(timeout=0.3) is False


def _pages():
    blog = {"type": "blog-post", "blog": '"Combinatorics and More"', "depth": "easy", "description": f'"{GOOD}"'}
    p = {f"post-{i}": ("", blog, f"# Post {i}\n") for i in range(5)}
    p["idea-x"] = ("", {"type": "idea", "description": f'"{GOOD}"'}, "# Idea X\n")
    p["kw-hit"] = ("", {"type": "idea"}, "# Keyword hit\n")
    return p


def test_related_caps_each_collection_and_skips_keyword_hits(monkeypatch):
    found = [("kw-hit", 0.99)] + [(f"post-{i}", 0.9 - i / 100) for i in range(5)] + [("idea-x", 0.5), ("gone", 0.4)]
    monkeypatch.setattr(qmd_client, "search", lambda q, limit=10, **k: found)
    out = svc.related("q", _pages(), exclude={"kw-hit"})
    ids = [h["id"] for h in out]
    assert ids == ["post-0", "post-1", "post-2", "idea-x"]          # 3 per collection; unknown slug dropped
    assert out[0]["snippet"] == GOOD and out[0]["depth"] == "easy"


def test_related_is_empty_when_service_is_down(monkeypatch):
    monkeypatch.setattr(qmd_client, "search", lambda *a, **k: None)
    assert svc.related("q", _pages()) == []


@pytest.mark.flag("semantic-search", True)
def test_search_adds_related_when_flag_on(monkeypatch):
    monkeypatch.setattr(svc, "related", lambda q, pages, exclude=(): [{"id": "x", "title": "X"}])
    assert svc.search("noise stability")["related"] == [{"id": "x", "title": "X"}]


@pytest.mark.flag("semantic-search", False)
def test_search_has_no_related_when_flag_off(monkeypatch):
    monkeypatch.setattr(svc, "related", lambda *a, **k: pytest.fail("qmd must not be called"))
    assert svc.search("noise stability")["related"] == []


def test_related_maps_qmd_keys_back_to_dotted_slugs(monkeypatch):
    pages = {"paper-x-et-al.-s-trick": ("", {"type": "paper", "description": f'"{GOOD}"'}, "# X\n"),
             "moc-a.canvas-llm": ("", {"type": "idea"}, "# M\n")}
    monkeypatch.setattr(qmd_client, "search", lambda *a, **k: [("paper-x-et-al-s-trick", 0.9), ("moc-a-canvas-llm", 0.8)])
    assert [h["id"] for h in svc.related("q", pages)] == ["paper-x-et-al.-s-trick", "moc-a.canvas-llm"]


def test_client_never_raises_on_bad_replies(monkeypatch):
    for reply in ([], None, {"hits": None}, {"hits": [{"slug": "a", "score": "high"}]}):
        monkeypatch.setattr(qmd_client, "_get", lambda path, timeout, r=reply: r)
        assert qmd_client.search("q") is None
    monkeypatch.setattr(qmd_client, "_get", lambda *a: (_ for _ in ()).throw(RuntimeError("torn")))
    assert qmd_client.search("q") is None and qmd_client.health() is None


def test_lint_never_writes_cards_outside_the_live_vault(tmp_path, monkeypatch):
    from kb_distillery.lint import lint
    monkeypatch.setattr(lint, "ROOT", str(tmp_path))
    monkeypatch.setattr(qmd_client, "refresh", lambda **k: pytest.fail("no refresh from a temp root"))
    lint.sync_search_cards()
    assert not (tmp_path / ".cache" / "qmd-cards").exists()
