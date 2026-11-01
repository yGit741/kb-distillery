"""The shell revalidates on every load; hashed assets are cached for good (a rebuilt app must not need a hard reload)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kb_distillery.api.spa import IMMUTABLE, NO_CACHE, spa_router


@pytest.fixture
def client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>shell</html>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    app = FastAPI()
    app.include_router(spa_router(str(tmp_path)))
    return TestClient(app)


def test_the_shell_is_revalidated_on_every_route(client):
    for path in ("/app", "/app/", "/app/relations", "/app/pages/some-slug", "/app/index.html"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers["cache-control"] == NO_CACHE, path


def test_hashed_assets_are_cached_for_good_on_both_routes(client):
    for path in ("/assets/index-abc123.js", "/app/assets/index-abc123.js"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == IMMUTABLE, path


def test_other_root_files_are_revalidated(client):
    assert client.get("/app/favicon.svg").headers["cache-control"] == NO_CACHE
