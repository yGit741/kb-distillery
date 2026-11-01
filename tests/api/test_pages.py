"""Page explorer routes: valid models on the real vault, legacy key parity, 404s, asset traversal."""
import pytest
from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.api.models.pages import PageDetail, PageIndex, PathResult, SearchResult
from kb_distillery.services import pages as svc


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def index(client):
    r = client.get("/api/pages")
    assert r.status_code == 200
    return r.json()


def test_index_model_and_legacy_keys(index):
    PageIndex.model_validate(index)
    legacy = svc.build_index()
    assert set(index) == set(legacy)
    assert len(index["pages"]) == len(legacy["pages"])
    assert set(index["pages"][0]) == set(legacy["pages"][0])    # incl. `in` / `out`
    assert index["wanted"] == [] or "from" in index["wanted"][0]


def test_page_detail_and_legacy_keys(client, index):
    slug = next(p["id"] for p in index["pages"] if p["out"])
    r = client.get(f"/api/pages/{slug}")
    assert r.status_code == 200
    body = r.json()
    PageDetail.model_validate(body)
    assert set(body) == set(svc.build_page(slug))
    assert body["card"]["id"] == slug


def test_page_unknown_is_404_with_legacy_shape(client):
    r = client.get("/api/pages/no-such-page-xyz")
    assert r.status_code == 404
    assert r.json() == {"error": "not found"}


def test_search(client, index):
    word = index["pages"][0]["title"].split()[0]
    r = client.get("/api/search", params={"q": word, "limit": "3"})
    assert r.status_code == 200
    body = r.json()
    SearchResult.model_validate(body)
    assert len(body["hits"]) <= 3
    assert set(body) == set(svc.search(word, 3))
    if body["hits"]:
        assert set(body["hits"][0]) == set(svc.search(word, 3)["hits"][0])


def test_search_short_query_is_empty_and_bad_limit_defaults(client):
    body = client.get("/api/search", params={"q": "a", "limit": "x"}).json()
    assert body == {"query": "a", "total": 0, "hits": [], "related": []}
    assert client.get("/api/search", params={"q": "ab", "limit": "nope"}).status_code == 200


def test_path_between_linked_pages(client, index):
    a, b = index["links"][0]
    r = client.get("/api/path", params={"a": a, "b": b})
    assert r.status_code == 200
    body = r.json()
    PathResult.model_validate(body)
    assert body["distance"] == 1 and body["paths"]
    hop = body["paths"][0]["hops"][0]
    assert set(hop) == {"from", "to", "dir", "context"}
    assert body == svc.find_paths(a, b)


def test_path_unknown_page_404(client, index):
    r = client.get("/api/path", params={"a": index["pages"][0]["id"], "b": "nope-xyz"})
    assert r.status_code == 404
    assert r.json() == {"error": "not found"}


def test_assets_refuse_traversal_and_unknown(client):
    assert client.get("/api/assets/vault", params={"name": "../../etc/passwd.png"}).status_code == 404
    assert client.get("/api/assets/vault", params={"name": "missing.png"}).status_code == 404
    assert client.get("/api/assets/vault", params={"name": "../../.git/config"}).status_code == 404
    assert client.get("/api/assets/chat", params={"path": "../../../etc/passwd.html"}).status_code == 404
    assert client.get("/api/assets/chat", params={"path": "meta/chats/assets/none.html"}).status_code == 404


def test_chat_asset_injects_height_reporter(client, tmp_path, monkeypatch):
    f = tmp_path / "v.html"
    f.write_text("<html><body>hi</body></html>")
    monkeypatch.setattr(svc, "resolve_chat_asset", lambda rel: str(f))
    r = client.get("/api/assets/chat", params={"path": "x.html"})
    assert r.status_code == 200 and "vizHeight" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_vault_asset_serves_image(client, tmp_path, monkeypatch):
    f = tmp_path / "p.png"
    f.write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(svc, "resolve_asset", lambda name: str(f))
    r = client.get("/api/assets/vault", params={"name": "p.png"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_mutation_without_loopback_origin_refused(client):
    r = client.post("/api/pages/x", headers={"Origin": "https://evil.example"})
    assert r.status_code in (403, 405)
