"""/api/review: the deck over HTTP (the deck logic itself is tests/proposals/test_review.py)."""
import tempfile
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from kb_distillery.proposals import service
from kb_distillery.server.app import create_app
from tests.proposals.test_review import ENV, make_kb

ORIGIN = {"Origin": "http://127.0.0.1:8765"}


def test_deck_and_apply_over_http(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    with tempfile.TemporaryDirectory() as tmp:
        root = str(make_kb(Path(tmp) / "kb"))
        monkeypatch.setattr(service, "DEFAULT_ROOT", root)
        with mock.patch("kb_distillery.ops.core.run_lint", return_value=None), \
                mock.patch("kb_distillery.ops.core.okf_gate", return_value=None), \
                mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"):
            text = Path(root, "wiki", "alpha.md").read_text(encoding="utf-8").replace("strong", "weaker")
            p = service.create("One edit", [{"kind": "edit_page", "slug": "alpha", "new_text": text}], root=root)
            with TestClient(create_app()) as c:
                deck = c.get("/api/review/deck")
                assert deck.status_code == 200, deck.text
                cards = deck.json()["cards"]
                assert [c_["proposal_id"] for c_ in cards] == [p["id"]]
                body = {"items": [{"proposal_id": p["id"], "decisions": [{"hunk_id": cards[0]["hunk"]["id"], "decision": "accept"}]}]}
                out = c.post("/api/review/apply", json=body, headers=ORIGIN)
                assert out.status_code == 200, out.text
                assert [a["id"] for a in out.json()["applied"]] == [p["id"]]
                assert c.post("/api/review/split", json={"slug": "nope"}, headers=ORIGIN).status_code in (400, 404)
        assert "weaker" in Path(root, "wiki", "alpha.md").read_text(encoding="utf-8")
