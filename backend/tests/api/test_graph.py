"""GET /api/graph: valid model on the real vault, key set equal to the legacy builder's, layer handling."""
import pytest
from fastapi.testclient import TestClient

from kb.api.app import create_app
from kb.api.models.graph import GraphSnapshot
from kb.services.graph import build_graph_snapshot


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def legacy():
    return build_graph_snapshot()


def test_graph_valid_model_and_legacy_keys(client, legacy):
    r = client.get("/api/graph")
    assert r.status_code == 200
    body = r.json()
    GraphSnapshot.model_validate(body)
    assert set(body) - {"layer", "kbs", "relations"} == set(legacy)   # `schema` keeps its legacy key via the alias
    assert body["node_count"] == len(body["nodes"]) == legacy["node_count"]
    assert body["link_count"] == len(body["links"])
    assert {k for n in body["nodes"] for k in n} >= {"id", "layer", "depth", "inDegree", "path"}
    assert body.get("layer") is None


def test_graph_node_vocabulary(client):
    layers = {n["layer"] for n in client.get("/api/graph").json()["nodes"]}
    assert layers <= {"source", "collection", "concept", ""}


def test_graph_raw_layer_adds_data_layer(client, legacy):
    r = client.get("/api/graph", params={"layer": "raw"})
    assert r.status_code == 200
    body = r.json()
    GraphSnapshot.model_validate(body)
    assert body["layer"] == "raw"
    assert set(body) >= set(legacy)
    assert body["etag"] != legacy["etag"]


def test_graph_unknown_layer_is_the_plain_graph(client, legacy):
    body = client.get("/api/graph", params={"layer": "bogus"}).json()
    assert body.get("layer") is None
    assert body["etag"] == legacy["etag"]


def test_graph_is_typed_in_openapi(client):
    spec = client.get("/openapi.json").json()
    ref = spec["paths"]["/api/graph"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert ref["$ref"].endswith("GraphSnapshot")


@pytest.mark.flag("graph-relations", False)
def test_graph_relations_flag_off_keeps_the_payload():
    with TestClient(create_app()) as c:
        body = c.get("/api/graph").json()
    assert body["relations"] is None
    assert all(set(l) == {"source", "target", "kind"} for l in body["links"])


@pytest.mark.flag("graph-relations", True)
def test_graph_relations_flag_on_adds_typed_relations():
    with TestClient(create_app()) as c:
        body = c.get("/api/graph").json()
        spec = c.get("/openapi.json").json()
    snap = GraphSnapshot.model_validate(body)
    assert snap.relations is not None
    assert all(set(l) == {"source", "target", "kind"} for l in body["links"])          # links stay as they were
    mentions = {(r.source, r.target) for r in snap.relations if r.kind == "mentions"}
    assert mentions == {(l["source"], l["target"]) for l in body["links"] if l["kind"] in ("wikilink", "related")}
    assert {r.origin for r in snap.relations} <= {"stored", "computed"}
    keys = [(r.source, r.target, r.kind) for r in snap.relations]
    assert len(keys) == len(set(keys))
    assert set(spec["components"]["schemas"]["GraphRelation"]["required"]) >= {"source", "target", "kind", "origin"}
