"""Free text → Cypher + style: raw passthrough, pure style, the LLM path (faked at `kb_distillery.llm.run`)."""
import json

import pytest

from kb_distillery import llm
from kb_distillery.graph import query as cypher
from kb_distillery.graph import shape_translate as st
from kb_distillery.graph.shape import ShapeError

SNAP = {
    "nodes": [{"id": "tensor-rank", "title": "Tensor rank", "type": "idea", "layer": "concept", "year": None},
              {"id": "attention", "title": "Attention", "type": "idea", "layer": "concept", "year": 2024},
              {"id": "paper-a", "title": "A", "type": "paper", "layer": "source", "year": 2023},
              {"id": "paper-b", "title": "B", "type": "paper", "layer": "source"}],
    "links": [{"source": "paper-a", "target": "tensor-rank", "kind": "wikilink"},
              {"source": "paper-b", "target": "attention", "kind": "wikilink"}],
}
RANK = 'MATCH (p:Paper)-[:MENTIONS]->(i:Idea) WHERE i.slug CONTAINS "tensor-rank" RETURN p.slug'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv(llm.ENV_BACKEND, raising=False)
    monkeypatch.setattr(cypher, "REJECTED_LOG", str(tmp_path / "rejected.jsonl"))
    monkeypatch.setattr(cypher, "current_graph", lambda: cypher.to_graph(SNAP))
    monkeypatch.setattr(llm, "run", lambda *a, **k: pytest.fail("unexpected LLM call"))


class FakeLLM:
    """Stands in for llm.run: replies popped in order (a str is the model text, a Result is passed through)."""

    def __init__(self, monkeypatch, *replies):
        self.replies, self.calls = list(replies), []
        monkeypatch.setattr(llm, "run", self)

    def __call__(self, requests, backend=None, **kw):
        self.calls.append({"request": requests[0], "backend": backend, **kw})
        r = self.replies.pop(0)
        if isinstance(r, llm.Result):
            return [r]
        return [llm.Result(id=requests[0].id, text=r, backend=llm.resolve_backend(backend), usd=0.01)]


def reply(cy=RANK, style="group by layer", ex="Papers on tensor rank."):
    return json.dumps({"cypher": cy, "style_text": style, "explanation": ex})


# --- no LLM --------------------------------------------------------------------------------------------
def test_raw_cypher_with_style_clause():
    out = st.shape(RANK + "\n-- colour by type; layout grid")
    assert out["cypher"] == RANK and out["source"] == "cypher" and out["backend"] is None and out["usd"] is None
    assert out["style"]["colour_by"] == {"by": "prop", "name": "type"} and out["style"]["layout"] == "grid"
    assert out["style_text"] == "colour by type; layout grid"
    assert out["columns"] == ["p.slug"] and out["rows"] == [["paper-a"]] and out["row_count"] == 1
    assert out["warnings"] == []


def test_raw_cypher_zero_rows_warns_and_error_is_a_hint():
    out = st.shape('match (p:Paper) where p.slug = "nope" return p.slug')
    assert out["rows"] == [] and any("row_count is 0" in w for w in out["warnings"])
    with pytest.raises(ShapeError) as e:
        st.shape("MATCH (a)-[r]-(b) RETURN b.slug")
    assert e.value.status == 422 and "neighbourhood" in str(e.value)


def test_raw_cypher_bad_style_is_rejected_with_the_grammar():
    with pytest.raises(ShapeError) as e:
        st.shape(RANK + "\nstyle: wobble the nodes")
    assert "unknown style clause `wobble the nodes`" in str(e.value) and "layout <force" in str(e.value)


def test_pure_style_keeps_the_node_set():
    out = st.shape("colour by degree; size by degree\nlayout radial")
    assert out["cypher"] is None and out["source"] == "cypher" and out["rows"] == [] and out["row_count"] == 0
    assert out["warnings"] == [] and out["style"]["layout"] == "radial"


def test_row_limit_is_applied_and_reported():
    out = st.shape("MATCH (n) RETURN n.slug", limit=2)
    assert out["row_count"] == 2 and out["truncated"] and any("cut at 2 rows" in w for w in out["warnings"])


def test_empty_text():
    with pytest.raises(ShapeError, match="empty request"):
        st.shape("   ")


# --- the LLM path --------------------------------------------------------------------------------------
def test_llm_happy_path(monkeypatch):
    fake = FakeLLM(monkeypatch, "Here you go:\n```json\n" + reply() + "\n```")
    out = st.shape("show papers that mention tensor rank, group by source, colour by type")
    assert out["source"] == "llm" and out["cypher"] == RANK and out["rows"] == [["paper-a"]]
    assert out["style"]["group_by"] == {"by": "prop", "name": "layer"} and out["explanation"] == "Papers on tensor rank."
    assert out["backend"] == "subscription" and out["usd"] == 0.01 and out["warnings"] == []
    (call,) = fake.calls
    p = call["request"].prompt
    assert call["backend"] == "subscription" and call["request"].model == "haiku"
    assert "show papers that mention tensor rank" in p and "undirected patterns" in p       # request + Cypher subset
    assert "Paper (2)" in p and "MENTIONS (2)" in p                                       # this kb's labels and kinds
    assert "group by <prop|label|edge-kind>" in p and p.count("Request: ") == len(st.EXAMPLES) + 1


def test_llm_zero_rows_warns(monkeypatch):
    FakeLLM(monkeypatch, reply('MATCH (p:Paper) WHERE p.slug = "nope" RETURN p.slug', ""))
    out = st.shape("papers called nope")
    assert out["row_count"] == 0 and any("row_count is 0" in w for w in out["warnings"])


def test_llm_style_only_reply_has_no_cypher(monkeypatch):
    FakeLLM(monkeypatch, reply("", "layout grid"))
    out = st.shape("tidy it up into a grid please")
    assert out["cypher"] is None and out["style"]["layout"] == "grid" and out["source"] == "llm"


def test_llm_bad_cypher_is_retried_with_the_error_then_422(monkeypatch):
    bad = "MATCH (a:Paper)-[r]-(b) RETURN b.slug"
    fake = FakeLLM(monkeypatch, reply(bad), reply(bad))
    with pytest.raises(ShapeError) as e:
        st.shape("papers next to something")
    assert e.value.status == 422 and "neighbourhood" in str(e.value) and "could not turn that into a valid view" in str(e.value)
    assert len(fake.calls) == 2
    retry = fake.calls[1]["request"].prompt
    assert "It was rejected: undirected patterns" in retry and bad in retry


def test_llm_retry_can_succeed(monkeypatch):
    fake = FakeLLM(monkeypatch, reply("MATCH (p:Paper)-[:OOPS]-(q) RETURN p.slug"), reply(),
                   )
    out = st.shape("papers about tensor rank")
    assert out["source"] == "llm" and out["row_count"] == 1 and len(fake.calls) == 2
    assert out["usd"] == 0.02                                # both calls are billed


def test_llm_bad_style_and_bad_json_are_retried(monkeypatch):
    fake = FakeLLM(monkeypatch, reply(RANK, "paint it blue"), "sorry, I cannot", reply())
    with pytest.raises(ShapeError) as e:
        st.shape("papers about tensor rank, blue please")
    assert "not a JSON object" in str(e.value) and len(fake.calls) == 2
    assert "unknown style clause `paint it blue`" in fake.calls[1]["request"].prompt
    FakeLLM(monkeypatch, reply(RANK, "paint it blue"), reply())
    assert st.shape("papers about tensor rank, blue please")["source"] == "llm"


def test_backend_override_and_env(monkeypatch):
    fake = FakeLLM(monkeypatch, reply(), reply(), reply())
    st.shape("papers about tensor rank", backend="api")
    monkeypatch.setenv(llm.ENV_BACKEND, "batch")
    out = st.shape("papers about tensor rank")
    st.shape("papers about tensor rank", backend="subscription")
    assert [c["backend"] for c in fake.calls] == ["api", "batch", "subscription"]
    assert out["backend"] == "batch"
    assert "wait_s" in fake.calls[1] and "wait_s" not in fake.calls[0]        # only a batch has a bounded wait


def test_unknown_backend_is_a_400_before_any_work(monkeypatch):
    with pytest.raises(ShapeError) as e:
        st.shape("papers about tensor rank", backend="gpt")
    assert e.value.status == 400 and "unknown backend" in str(e.value)
    monkeypatch.setenv(llm.ENV_BACKEND, "bogus")
    with pytest.raises(ShapeError) as e:
        st.shape("papers about tensor rank")
    assert e.value.status == 400


def test_llm_failure_is_a_502(monkeypatch):
    FakeLLM(monkeypatch, llm.Result(id="shape", error="no API key", backend="api"))
    with pytest.raises(ShapeError) as e:
        st.shape("papers about tensor rank", backend="api")
    assert e.value.status == 502 and "no API key" in str(e.value)


def test_examples_run_on_the_engine():
    """The few-shot examples must be queries the engine accepts, and their style must parse."""
    from kb_distillery.graph.shape import parse_style
    g = cypher.to_graph(SNAP)
    for _, cy, style, _ in st.EXAMPLES:
        cypher.run(cy, graph=g)
        parse_style(style)


# --- CLI parity ----------------------------------------------------------------------------------------
def test_cli_shape_prints_the_json(monkeypatch, capsys):
    from kb_distillery.search import cypher as cli
    FakeLLM(monkeypatch, reply())
    assert cli.main(["shape", "papers about tensor rank", "--backend", "api"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["source"] == "llm" and out["backend"] == "api" and out["rows"] == [["paper-a"]]
    assert cli.main(["shape", "layout grid"]) == 0
    assert json.loads(capsys.readouterr().out)["cypher"] is None


def test_cli_shape_error_exits_2(capsys):
    from kb_distillery.search import cypher as cli
    assert cli.main(["shape", RANK + "\n-- layout spiral"]) == 2
    assert "layout is one of" in capsys.readouterr().err
