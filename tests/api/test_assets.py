"""GET /api/static/{name} — the dashboard's css/js only; traversal is a 404."""
import os

import pytest
from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.dashboard.serve import STATIC_DIR


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def test_serves_existing_static_files(client):
    files = [f for f in os.listdir(STATIC_DIR) if os.path.isfile(os.path.join(STATIC_DIR, f))]
    assert files
    for f in files:
        r = client.get(f"/api/static/{f}")
        legacy = open(os.path.join(STATIC_DIR, f), "rb").read()
        assert r.status_code == 200 and r.content == legacy
        assert r.headers["content-type"].startswith("text/css" if f.endswith(".css") else "application/javascript")


@pytest.mark.parametrize("name", ["nope.js", "..%2Fserve.py", "../serve.py", "..%2F..%2Fserve.py",
                                  "%2Fetc%2Fpasswd", "sub/../../serve.py"])
def test_missing_and_traversal_refused(client, name):
    assert client.get(f"/api/static/{name}").status_code == 404
