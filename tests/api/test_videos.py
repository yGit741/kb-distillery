"""GET /api/videos/{path}: a bundle's data with anchor raw paths; anything else is 404."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.api.models.videos import VideoBundle
from kb_distillery.services import corpus

DATA = {"id": "abcdefghijk", "title": "SVM", "url": "https://www.youtube.com/watch?v=abcdefghijk", "channel": "MIT",
        "duration": 600, "description": "d", "links": [], "chapters": [{"title": "Intro", "start": 0, "end": 600}],
        "comments": [], "subs_kind": "manual",
        "sections": [{"chapter": "Intro", "start": 0, "end": 600, "text": "Hello."}],
        "anchors": [{"t": 42, "thumb": "a-00042.jpg", "kind": "board", "score": 5, "why": ["board-erase"], "ocr": []}],
        "stats": {}}


@pytest.fixture
def vault(tmp_path):
    d = tmp_path / "raw" / "videos" / "svm"
    d.mkdir(parents=True)
    (d / "video.md").write_text("# SVM\n")
    (d / "video.json").write_text(json.dumps(DATA))
    old = tmp_path / "raw" / "videos" / "old"
    old.mkdir()
    (old / "video.md").write_text("# old\n")
    (old / "video.json").write_text(json.dumps({**{k: v for k, v in DATA.items() if k != "anchors"},
                                                "tier": "vibe", "frames": [{"t": 1, "file": "frame-00001.jpg"}]}))
    (tmp_path / "raw" / "printed-docs").mkdir()
    (tmp_path / "raw" / "printed-docs" / "2000-x.md").write_text("x")
    with mock.patch.object(corpus, "ROOT", str(tmp_path)):
        yield tmp_path


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def test_a_bundle_by_its_item_or_folder(client, vault):
    for path in ("raw/videos/svm/video.md", "videos/svm/video.md", "raw/videos/svm"):
        r = client.get(f"/api/videos/{path}")
        assert r.status_code == 200, path
        body = VideoBundle.model_validate(r.json())
        assert body.anchors[0].path == "raw/videos/svm/a-00042.jpg" and body.raw == "raw/videos/svm/video.md"


def test_a_bundle_from_before_anchors_still_loads_without_them(client, vault):
    body = VideoBundle.model_validate(client.get("/api/videos/raw/videos/old/video.md").json())
    assert body.anchors == [] and "frames" not in body.model_dump()


def test_not_a_bundle_is_404(client, vault):
    for path in ("raw/printed-docs/2000-x.md", "raw/videos/nope/video.md", "raw/videos/../../etc/passwd"):
        assert client.get(f"/api/videos/{path}").status_code == 404, path
