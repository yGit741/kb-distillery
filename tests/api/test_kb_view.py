"""Read-only views of other knowledge bases: /api/graph?kb=… and /api/pages/{slug}?kb=…"""
import os

import pytest
from fastapi.testclient import TestClient

from kb_distillery import kbconfig
from kb_distillery.api.app import create_app
from kb_distillery.services import kbview

TYPES = """
[types.collection.book]
label = "Books"
[types.source.part]
label = "Parts"
[types.concept.topic]
label = "Topics"
[types.concept.idea]
label = "Ideas"
[types.source.paper]
label = "Papers"
"""
OTHER_TYPES = """
[types.concept.idea]
label = "Ideas"
[types.source.topic]
label = "Topic notes"
"""


def _kb(root, kb_id, types, pages):
    os.makedirs(os.path.join(root, "wiki"))
    with open(os.path.join(root, "kb.toml"), "w", encoding="utf-8") as f:
        f.write(f'[kb]\nid = "{kb_id}"\nname = "{kb_id.title()}"\nschema_version = "1.5"\n{types}')
    for slug, (ptype, body) in pages.items():
        with open(os.path.join(root, "wiki", f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(f"---\ntype: {ptype}\n---\n\n# {slug.title()}\n\n{body}\n")


@pytest.fixture
def two_kbs(tmp_path, monkeypatch):
    a, b = str(tmp_path / "kb-alpha"), str(tmp_path / "kb-beta")
    _kb(a, "alpha", TYPES, {"shared": ("idea", "Links [[only-alpha]]."), "only-alpha": ("idea", "Back to [[shared]].")})
    _kb(b, "beta", OTHER_TYPES, {"shared": ("idea", "Links [[note]]."), "note": ("topic", "A note.")})
    with open(os.path.join(a, "wiki", "book-x.md"), "w", encoding="utf-8") as f:
        f.write("---\ntype: book\n---\n\n# Book X\n")
    with open(os.path.join(a, "wiki", "book-x-ch1.md"), "w", encoding="utf-8") as f:
        f.write("---\ntype: part\nbook: book-x\n---\n\n# Chapter 1\n")
    monkeypatch.setattr(kbconfig, "discover", lambda: {"alpha": a, "beta": b})
    kbview._views.clear()
    with TestClient(create_app()) as c:
        yield c
    kbview._views.clear()


def test_no_kb_param_is_unchanged(two_kbs):
    j = two_kbs.get("/api/graph").json()
    assert len(j["kbs"]) == 1 and j["kbs"][0]["active"]
    assert all(n["id"] == n["slug"] for n in j["nodes"])


@pytest.mark.flag("kb-view", True)
def test_one_other_kb_keeps_bare_slugs(two_kbs):
    j = two_kbs.get("/api/graph?kb=alpha").json()
    assert j["kbs"] == [{"id": "alpha", "name": "Alpha", "active": False}]
    assert sorted(n["id"] for n in j["nodes"]) == ["book-x", "book-x-ch1", "only-alpha", "shared"]
    assert {n["kb"] for n in j["nodes"]} == {"alpha"}
    assert {"source": "shared", "target": "only-alpha", "kind": "wikilink"} in j["links"]


@pytest.mark.flag("kb-view", True)
def test_several_kbs_namespace_ids_and_types(two_kbs):
    j = two_kbs.get("/api/graph?kb=alpha,beta").json()
    ids = sorted(n["id"] for n in j["nodes"])
    assert ids == ["alpha:book-x", "alpha:book-x-ch1", "alpha:only-alpha", "alpha:shared", "beta:note", "beta:shared"]
    assert all(n["id"] == f'{n["kb"]}:{n["slug"]}' for n in j["nodes"])
    assert {l["source"] for l in j["links"]} <= set(ids) and {l["target"] for l in j["links"]} <= set(ids)
    # `topic` is a concept in alpha but a source in beta: beta's gets its own type, never alpha's colour
    note = next(n for n in j["nodes"] if n["id"] == "beta:note")
    assert note["type"] == "beta:topic" and note["layer"] == "source"
    by_id = {t["id"]: t for t in j["schema"]["types"]}
    assert by_id["topic"]["layer"] == "concept" and by_id["beta:topic"]["layer"] == "source"
    assert "beta:topic" in j["schema"]["source_types"]
    assert by_id["idea"]["layer"] == "concept"     # agreeing types are shared
    assert [k["id"] for k in j["kbs"]] == ["alpha", "beta"]
    # a part's book is namespaced like the ids, so the canvas finds it
    part = next(n for n in j["nodes"] if n["id"] == "alpha:book-x-ch1")
    assert part["part"]["book"] == "alpha:book-x"
    # default types follow the renames: beta's source-layer `topic` is not shown by default as a concept
    assert "beta:topic" not in j["schema"]["default_visible"] and "topic" in j["schema"]["default_visible"]


@pytest.mark.flag("kb-view", True)
def test_unknown_kb_404_and_no_path_lookup(two_kbs):
    assert two_kbs.get("/api/graph?kb=nope").status_code == 404
    assert two_kbs.get("/api/graph?kb=../kb-alpha").status_code == 404
    assert two_kbs.get("/api/pages/shared?kb=nope").status_code == 404


@pytest.mark.flag("kb-view", False)
def test_flag_off_serves_no_other_kb(two_kbs):
    assert two_kbs.get("/api/graph?kb=alpha").status_code == 404
    assert two_kbs.get("/api/pages/shared?kb=beta").status_code == 404
    assert two_kbs.get("/api/graph").status_code == 200


@pytest.mark.flag("kb-view", True)
def test_raw_layer_only_for_the_active_kb(two_kbs):
    assert two_kbs.get("/api/graph?kb=alpha&layer=raw").status_code == 400


@pytest.mark.flag("kb-view", True)
def test_page_from_another_kb_is_read_only(two_kbs):
    j = two_kbs.get("/api/pages/shared?kb=beta").json()
    assert j["kb"] == "beta" and j["read_only"] is True
    assert j["outbound"] == ["note"]
    assert two_kbs.get("/api/pages/only-alpha?kb=beta").status_code == 404
    idx = two_kbs.get("/api/pages?kb=beta").json()
    assert sorted(c["id"] for c in idx["pages"]) == ["note", "shared"]
    assert two_kbs.get("/api/pages?kb=nope").status_code == 404


def test_no_write_endpoint_takes_kb():
    app = create_app()
    for route in app.routes:
        methods = getattr(route, "methods", set()) or set()
        if methods & {"POST", "PUT", "PATCH", "DELETE"}:
            params = {p.name for p in getattr(route, "dependant").query_params} if hasattr(route, "dependant") else set()
            assert "kb" not in params, route.path
