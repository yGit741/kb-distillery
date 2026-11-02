"""GET /api/static/{name} — the dashboard's css/js only; traversal is a 404."""
import os

import pytest
from fastapi.testclient import TestClient

from kb_distillery.api.app import create_app
from kb_distillery.api.assets import STATIC_DIR


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


def test_app_and_assets_load_without_the_legacy_dashboard():
    """The app serves without kb_distillery.dashboard: the dashboard imports from api.assets, never the reverse."""
    import subprocess
    import sys
    code = ("import sys; from kb_distillery.api.app import create_app; from kb_distillery.api import assets;"
            "from kb_distillery.publish import site_state; create_app();"
            "bad=[m for m in sys.modules if m.startswith('kb_distillery.dashboard')]; assert not bad, bad;"
            "assert assets.VIZ_REPORTER.startswith(b'<script>') and callable(assets.thumbnail_png)")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-800:]
