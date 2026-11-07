"""graph.layers_translate: the prompt, the answer check, the printed lines. `kb_distillery.llm.ask` is faked."""
import json

import pytest

from kb_distillery import llm
from kb_distillery.graph import layers_translate as lt
from kb_distillery.graph import query as cypher

SNAP = {
    "nodes": [{"id": "a", "title": "Learning theory", "type": "idea", "layer": "concept", "areas": ["ml"]},
              {"id": "b", "title": "Attention", "type": "paper", "layer": "source"}],
    "links": [{"source": "b", "target": "a", "kind": "wikilink"}],
}
VOCAB = {"node_types": {"idea": 1, "paper": 1}, "edge_types": {"supports": 2}, "areas": {"ml": 1}, "titles": ["Learning theory"]}
GOOD = {"layers": [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "hops", "of": "Learning theory", "n": 2}]}}],
        "explanation": "pages near it"}


def fake_ask(monkeypatch, *replies, usd=0.0, used=None, **extra):
    seen, queue = [], list(replies)

    def ask(prompt, backend=None, fallback=None, run_kw=None, **kw):
        seen.append({"prompt": prompt, "backend": backend, "fallback": fallback, "run_kw": run_kw, **kw})
        text = queue.pop(0)
        return llm.Result(id="layers", text=text if isinstance(text, str) else json.dumps(text), usd=usd,
                          backend=backend, backend_used=used or backend or "subscription", **extra)
    monkeypatch.setattr(llm, "ask", ask)
    return seen


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(llm.ENV_BACKEND, raising=False)


def test_translate_returns_layers_lines_and_the_backend(monkeypatch):
    seen = fake_ask(monkeypatch, GOOD)
    out = lt.translate("things near learning theory", vocabulary=VOCAB)
    assert [l.model_dump(exclude_none=True)["subgraph"] for l in out["layers"]] == [GOOD["layers"][0]["subgraph"]]
    assert out["lines"] == ['show nodes within 2 hops of "Learning theory"']
    assert out["layers"][0].id == "llm-1" and out["layers"][0].text == ""
    assert out["backend"] == "subscription" and out["usd"] == 0 and out["explanation"] == "pages near it"
    # one prompt: the grammar, this kb's vocabulary, and the request; subscription falls back to api by default
    p = seen[0]["prompt"]
    assert "within <n> hops of" in p and "Learning theory" in p and "supports (2)" in p and "things near learning theory" in p
    assert "Cypher" in p and "never Cypher" in p
    assert seen[0]["backend"] == "subscription" and seen[0]["fallback"] == "api" and seen[0]["run_kw"] is None


def test_the_reply_may_wrap_json_in_prose_and_style_words_are_normalized(monkeypatch):
    reply = "Sure:\n```json\n" + json.dumps({"layers": [{"kind": "style", "target": "nodes", "style": {"color": "year", "size": "degree"}}]}) + "\n```"
    fake_ask(monkeypatch, reply)
    out = lt.translate("colour by year", vocabulary=VOCAB)
    assert out["layers"][0].style.color.by == "year" and out["layers"][0].style.size.by == "degree"
    assert out["lines"] == ["style nodes color by year"]


@pytest.mark.parametrize("reply, why", [
    ("I cannot do that", "not a JSON object"),
    ({"layers": []}, "no layers"),
    ({"layers": [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [{"t": "cypher", "q": "MATCH (n)"}]}}]}, "not a valid list of layers"),
    ({"layers": [{"kind": "explode", "target": "nodes"}]}, "not a valid list of layers"),
    ({"layers": [{"kind": "show", "target": "nodes", "extra": 1}]}, "not a valid list of layers"),
])
def test_an_answer_that_does_not_validate_is_a_422_with_the_raw_text(monkeypatch, reply, why):
    fake_ask(monkeypatch, reply)
    with pytest.raises(lt.LayersError) as e:
        lt.translate("whatever", vocabulary=VOCAB)
    assert e.value.status == 422 and why in str(e.value) and "answer:" in str(e.value)


def test_backend_choices(monkeypatch):
    seen = fake_ask(monkeypatch, GOOD, GOOD, GOOD, GOOD)
    lt.translate("x", vocabulary=VOCAB, backend="api")
    lt.translate("x", vocabulary=VOCAB, backend="subscription", fallback="none")
    lt.translate("x", vocabulary=VOCAB, backend="batch")
    monkeypatch.setenv(llm.ENV_BACKEND, "api")
    lt.translate("x", vocabulary=VOCAB)
    assert [(s["backend"], s["fallback"]) for s in seen] == [("api", None), ("subscription", None), ("batch", None), ("api", None)]
    assert seen[2]["run_kw"] == {"wait_s": lt.BATCH_WAIT_S, "poll_every": lt.BATCH_POLL_S}


def test_bad_backend_is_a_400_and_a_backend_failure_a_502(monkeypatch):
    with pytest.raises(lt.LayersError) as e:
        lt.translate("x", vocabulary=VOCAB, backend="nope")
    assert e.value.status == 400
    with pytest.raises(lt.LayersError) as e:
        lt.translate("x", vocabulary=VOCAB, backend="api", fallback="nope")
    assert e.value.status == 400
    monkeypatch.setattr(llm, "ask", lambda *a, **k: llm.Result(id="layers", error="rate limited", backend="api"))
    with pytest.raises(lt.LayersError) as e:
        lt.translate("x", vocabulary=VOCAB, backend="api")
    assert e.value.status == 502 and "rate limited" in str(e.value)
    monkeypatch.setattr(llm, "ask", lambda *a, **k: (_ for _ in ()).throw(llm.HTTPFail(0, "no route")))
    with pytest.raises(lt.LayersError) as e:
        lt.translate("x", vocabulary=VOCAB, backend="batch")
    assert e.value.status == 502


def test_empty_text_is_a_422():
    with pytest.raises(lt.LayersError) as e:
        lt.translate("  ", vocabulary=VOCAB)
    assert e.value.status == 422


def test_the_fallback_is_reported(monkeypatch):
    fake_ask(monkeypatch, GOOD, usd=0.0007, used="api", fallback_from="subscription")
    out = lt.translate("x", vocabulary=VOCAB)
    assert out["backend"] == "api" and out["fallback_from"] == "subscription" and out["usd"] == 0.0007


def test_names_that_the_kb_does_not_have_become_warnings(monkeypatch):
    bad = {"layers": [{"kind": "show", "target": "nodes", "subgraph": {"nodes": [
        {"t": "type", "value": ["paper", "gizmo"]}, {"t": "inArea", "area": "chem"}, {"t": "hasEdge", "type": "refutes"}]}},
        {"kind": "hide", "target": "edges", "subgraph": {"edges": [{"t": "type", "value": "sibling"}]}}]}
    fake_ask(monkeypatch, bad)
    w = lt.translate("x", vocabulary=VOCAB)["warnings"]
    assert len(w) == 4 and any("gizmo" in x for x in w) and any("chem" in x for x in w) and any("refutes" in x for x in w)


def test_vocabulary_reads_the_graph():
    v = lt.vocabulary(cypher.to_graph(SNAP))
    assert v["node_types"] == {"idea": 1, "paper": 1} and v["areas"] == {"ml": 1}
    assert set(v["titles"]) == {"Learning theory", "Attention"} and v["edge_types"]
