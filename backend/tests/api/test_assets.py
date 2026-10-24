"""GET /api/assets/{name} — images under raw/ only, by Obsidian embed name; traversal is a 404."""
import pytest
from fastapi.testclient import TestClient

from kb.api.app import create_app
from kb.services import pages

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "raw" / "images").mkdir(parents=True)
    (tmp_path / "raw" / "images" / "fig-01.png").write_bytes(PNG)
    (tmp_path / "raw" / "web-clips").mkdir()
    (tmp_path / "raw" / "web-clips" / "pic.svg").write_text("<svg/>")
    (tmp_path / "secret.png").write_bytes(PNG)
    (tmp_path / "raw" / "images" / "notes.md").write_text("x")
    monkeypatch.setattr(pages, "ROOT", str(tmp_path))
    with TestClient(create_app()) as c:
        yield c


def test_serves_image_with_type(client):
    r = client.get("/api/assets/fig-01.png")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert client.get("/api/assets/pic.svg").headers["content-type"] == "image/svg+xml"


def test_only_images_and_missing_404(client):
    assert client.get("/api/assets/notes.md").status_code == 404
    assert client.get("/api/assets/nope.png").status_code == 404


@pytest.mark.parametrize("name", ["..%2Fsecret.png", "../secret.png", "..%2F..%2Fsecret.png",
                                  "%2Fetc%2Fpasswd.png", "raw/../secret.png"])
def test_traversal_refused(client, name):
    assert client.get(f"/api/assets/{name}").status_code == 404
