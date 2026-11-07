"""What a share build bakes for the read-only half of the graph line: ready views (both profiles), the favorite marks of
pages the site carries, and pinned views on the private profile only. Fakes only: a temp folder, no network, no model."""
import json
import os
from unittest import mock

import pytest

from kb_distillery.publish.site import build


@pytest.fixture
def kb(tmp_path):
    meta = tmp_path / "meta"
    meta.mkdir()
    (meta / "views.json").write_text(json.dumps([{"id": "mine", "name": "My view", "created": "2026-11-01", "spec": {"v": 2, "layers": []}}]))
    (meta / "favorites.json").write_text(json.dumps({"v": 1, "slugs": ["kept", "cut"]}))
    with mock.patch.dict(os.environ, {"KB_ROOT": str(tmp_path)}):
        yield tmp_path


DATA = {"pages": {"kept": {}, "other": {}}}


def test_private_bakes_pinned_views_ready_views_and_the_marks_of_carried_pages(kb):
    out = build.bake_line_data(DATA, "private")
    assert [v["id"] for v in out["views"]] == ["mine"]
    assert out["favorites"] == ["kept"]
    assert isinstance(out["readyViews"], list)


def test_public_bakes_no_pinned_view_and_no_favorite_mark(kb):
    out = build.bake_line_data(DATA, "public")
    assert out["views"] == [] and out["favorites"] == []
    assert isinstance(out["readyViews"], list)


def test_a_damaged_file_does_not_stop_the_build(kb):
    (kb / "meta" / "views.json").write_text("{not json")
    out = build.bake_line_data(DATA, "private")
    assert out["views"] == [] and out["favorites"] == []


def test_a_kb_without_views_or_favorites_bakes_empty_lists(tmp_path):
    with mock.patch.dict(os.environ, {"KB_ROOT": str(tmp_path)}):
        out = build.bake_line_data(DATA, "private")
    assert out["views"] == [] and out["favorites"] == []
