"""GET /api/videos/{path}: a bundle's data with frame raw paths; anything else is 404."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from kb.api.app import create_app
from kb.api.models.videos import VideoBundle
from kb.services import corpus

DATA = {"id": "abcdefghijk", "title": "SVM", "url": "https://www.youtube.com/watch?v=abcdefghijk", "channel": "MIT",
        "duration": 600, "description": "d", "links": [], "chapters": [{"title": "Intro", "start": 0, "end": 600}],
        "comments": [], "subs_kind": "manual", "tier": "vibe",
        "sections": [{"chapter": "Intro", "start": 0, "end": 600, "text": "Hello."}],
        "frames": [{"t": 42, "file": "frame-00042.jpg", "kind": "vibe", "ocr": ["SVM"], "conf": 0.9}], "stats": {}}


@pytest.fixture
def vault(tmp_path):
    d = tmp_path / "raw" / "videos" / "svm"
    d.mkdir(parents=True)
    (d / "video.md").write_text("# SVM\n")
    (d / "video.json").write_text(json.dumps(DATA))
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
        assert body.frames[0].path == "raw/videos/svm/frame-00042.jpg" and body.raw == "raw/videos/svm/video.md"


def test_not_a_bundle_is_404(client, vault):
    for path in ("raw/printed-docs/2000-x.md", "raw/videos/nope/video.md", "raw/videos/../../etc/passwd"):
        assert client.get(f"/api/videos/{path}").status_code == 404, path
