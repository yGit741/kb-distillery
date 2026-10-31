"""kb.graph.propose: kinds and gates, validation, prompt, and submit/collect/review against a fake kb.llm."""
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from kb import llm
from kb.graph import propose

PAGES = {
    "paper-a": ("paper", "full", "Paper A", "related: [q-1]",
                "**Problem:** the A problem.\n\n**Main result:** A extends [[paper-b]] via [[idea-x]].\n\n"
                "## My notes\n\nSECRET-MINE\n"),
    "paper-b": ("paper", "full", "Paper B", "", "**Problem:** B.\n"),
    "idea-x": ("idea", "", "Idea X", "", "An idea used by [[paper-a]].\n"),
    "q-1": ("question", "", "Question one", "", "## Question\n\nIs A true? See [[paper-a]].\n"),
    "blog-e": ("blog-post", "easy", "Blog E", "", "Mentions [[idea-x]] and [[q-1]].\n"),
    "person-p": ("person", "", "P", "", "Advised by [[person-q]].\n"),
    "person-q": ("person", "", "Q", "", "Advisor.\n"),
    "topic-t": ("topic", "", "Topic", "", "Links [[paper-a]].\n"),
}


def write_page(root, slug, typ, depth, title, extra, body):
    fm = [f"type: {typ}", "layer: x"] + ([f"depth: {depth}"] if depth else []) + ([extra] if extra else [])
    fm.append(f'summary: "Summary of {title}."')
    with open(os.path.join(root, "wiki", f"{slug}.md"), "w", encoding="utf-8") as f:
        f.write("---\n" + "\n".join(fm) + f"\n---\n\n# {title}\n\n{body}")


class FakeCfg:
    def __init__(self, edges):
        self.edges = edges

    def section(self, name):
        return self.edges if name == "edges" else {}


KC = propose.kind_config(FakeCfg({}))


@pytest.fixture
def vault(tmp_path, monkeypatch):
    os.makedirs(tmp_path / "wiki")
    for slug, spec in PAGES.items():
        write_page(str(tmp_path), slug, *spec)
    monkeypatch.setattr(propose, "ROOT", str(tmp_path))
    monkeypatch.setattr(propose, "kind_config", lambda cfg=None: KC)
    monkeypatch.setattr(propose, "load_vectors", lambda: None)
    monkeypatch.delenv(llm.ENV_BACKEND, raising=False)
    return tmp_path


def tree(root, skip=".cache"):
    """sha of every file outside `skip`: what a run must leave alone."""
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if os.path.relpath(os.path.join(d, x), root) != skip]
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    return out


def pages_of(vault):
    return propose.load_pages(str(vault))


# --- kinds, gates ---------------------------------------------------------------------------------------------
def test_default_kinds_and_declared_kinds_from_kb_toml():
    assert KC["kinds"] == propose.KINDS and KC["symmetric"] == {"contradicts"} and KC["note_required"] == {"contradicts"}
    kc = propose.kind_config(FakeCfg({"types": ["extends", "refutes"], "symmetric": ["refutes"]}))
    assert kc["kinds"] == ("extends", "refutes") and kc["symmetric"] == {"refutes"} and kc["note_required"] == set()


def test_type_gates():
    assert propose.gate_ok("extends", "paper", "idea") and propose.gate_ok("uses", "video", "blog-post")
    assert not propose.gate_ok("extends", "paper", "question")
    assert propose.gate_ok("example-of", "paper", "idea") and not propose.gate_ok("example-of", "paper", "paper")
    assert propose.gate_ok("open-problem-in", "question", "paper") and not propose.gate_ok("open-problem-in", "paper", "question")
    assert propose.gate_ok("addresses", "blog-post", "question") and not propose.gate_ok("addresses", "idea", "question")
    assert propose.gate_ok("student-of", "person", "person") and not propose.gate_ok("student-of", "paper", "person")
    assert propose.gate_ok("refutes", "anything", "else")                       # a declared kind without a gate
    assert propose.kinds_for("question", KC) == ["open-problem-in"]
    assert set(propose.kinds_for("paper", KC, easy=True)) == {"example-of", "addresses"}


# --- validation -----------------------------------------------------------------------------------------------
def test_confidence_is_data_so_weak_proposals_are_kept_unless_a_cutoff_is_asked_for(vault):
    pages = pages_of(vault)
    item = [{"to": "idea-x", "kind": "example-of", "confidence": 0.1, "evidence": "e"}]
    acc, rej = propose.validate("paper-a", item, ["idea-x"], pages, KC)
    assert [r["confidence"] for r in acc] == [0.1] and rej == []
    acc, rej = propose.validate("paper-a", item, ["idea-x"], pages, KC, keep_above=0.5)
    assert acc == [] and rej[0]["reason"].startswith("confidence 0.1")
    acc, _ = propose.validate("paper-a", [{"to": "idea-x", "kind": "example-of", "confidence": 1.4}], ["idea-x"], pages, KC)
    assert acc == []                                                              # outside 0..1 is still invalid


def test_validate_rules_and_symmetric_dedupe(vault):
    pages = pages_of(vault)
    cands = ["paper-b", "idea-x"]
    acc, rej = propose.validate("paper-a", [
        {"to": "paper-b", "kind": "extends", "confidence": 0.9, "evidence": "e"},
        {"to": "2", "kind": "uses", "confidence": 0.8},                          # numbered candidate → idea-x
        {"to": "[[paper-b]]", "kind": "contradicts", "note": "A says x, B says not x", "confidence": 0.7},
        {"to": "paper-b", "kind": "contradicts", "note": "again", "confidence": 0.7},     # duplicate pair
        {"to": "paper-b", "kind": "contradicts", "confidence": 0.9},                      # no note
        {"to": "q-1", "kind": "uses", "confidence": 0.9},                                 # not a candidate
        {"to": "paper-a", "kind": "uses", "confidence": 0.9},                             # self
        {"to": "paper-b", "kind": "addresses", "confidence": 0.9},                        # gate
        {"to": "paper-b", "kind": "cites", "confidence": 0.9},                            # unknown kind
        {"to": "idea-x", "kind": "example-of", "confidence": 0.3},                        # weak: kept by default
        {"to": "idea-x", "kind": "example-of", "confidence": "high"},                     # not a number
    ], cands, pages, KC, keep_above=0.5)
    assert [(r["from"], r["to"], r["kind"]) for r in acc] == [
        ("paper-a", "paper-b", "extends"), ("paper-a", "idea-x", "uses"), ("paper-a", "paper-b", "contradicts")]
    reasons = [r["reason"] for r in rej]
    assert reasons[0] == "duplicate" and reasons[1] == "contradicts needs a note"
    assert "not a candidate" in reasons[2] and reasons[3] == "self-relation"
    assert "does not join" in reasons[4] and "not allowed" in reasons[5]
    assert reasons[6].startswith("confidence 0.3") and "missing" in reasons[7]      # below an explicit keep_above

    acc, _ = propose.validate("paper-b", [{"to": "paper-a", "kind": "contradicts", "note": "n", "confidence": 0.6}],
                              ["paper-a"], pages, KC)
    assert (acc[0]["from"], acc[0]["to"]) == ("paper-a", "paper-b")              # symmetric: slugs in order


def test_parse_reply_shapes():
    assert propose.parse_reply('[{"to": "a"}]') == ([{"to": "a"}], "")
    assert propose.parse_reply('```json\n[]\n```') == ([], "")
    assert propose.parse_reply('Here you go: [{"to": "a"}, 3] done')[0] == [{"to": "a"}]
    assert propose.parse_reply('{"proposals": [{"to": "b"}]}')[0] == [{"to": "b"}]
    assert propose.parse_reply("no idea")[0] is None


# --- subjects, candidates, prompt -----------------------------------------------------------------------------
def test_subjects_and_candidates(vault):
    pages = pages_of(vault)
    assert [s for s, _ in propose.select(pages)] == ["idea-x", "paper-a", "paper-b", "q-1"]
    assert ("blog-e", True) in propose.select(pages, include_easy=True)
    assert "person-p" in dict(propose.select(pages, include_people=True))
    # outbound first (related q-1 via addresses); topic-t links paper-a but no kind reaches a topic
    assert propose.candidates("paper-a", pages, propose.kinds_for("paper", KC)) == ["idea-x", "paper-b", "q-1"]
    assert propose.candidates("q-1", pages, propose.kinds_for("question", KC)) == ["paper-a", "blog-e"]
    assert propose.candidates("paper-a", pages, propose.kinds_for("paper", KC), cap=1) == ["idea-x"]

    class Vecs:
        def neighbours(self, slug, k):
            return [("blog-e", float("nan")), ("paper-b", 0.9), ("idea-x", 0.8)]
    assert propose.candidates("idea-x", pages, propose.kinds_for("idea", KC), Vecs()) == ["paper-a", "paper-b", "blog-e"]  # NaN neighbour skipped; blog-e only as inbound


def test_prompt_lists_numbered_candidates_and_keeps_my_notes_out(vault):
    pages = pages_of(vault)
    kinds = propose.kinds_for("paper", KC)
    text = propose.build_prompt(pages["paper-a"], [pages["paper-b"], pages["idea-x"]], kinds, KC)
    assert "1. paper-b (paper) — Paper B: Summary of Paper B." in text and "2. idea-x (idea)" in text
    assert "SUBJECT: paper-a (paper) — Paper A" in text and "**Problem:** the A problem." in text
    assert "SECRET-MINE" not in text and "never invent a slug" in text and "Return []" in text
    assert "- contradicts:" in text and "open-problem-in" not in text
    assert len(propose.excerpt("x" * 5000)) == propose.EXCERPT


# --- submit / collect / review --------------------------------------------------------------------------------
def reply_for(slug):
    return {
        "paper-a": '[{"to": "paper-b", "kind": "extends", "note": "", "confidence": 0.9, "evidence": "A extends B"},'
                   ' {"to": "paper-b", "kind": "contradicts", "note": "A: x; B: not x", "confidence": 0.7, "evidence": ""},'
                   ' {"to": "idea-x", "kind": "uses", "confidence": 0.2}]',
        "paper-b": '[{"to": "paper-a", "kind": "contradicts", "note": "B: not x; A: x", "confidence": 0.8}]',
        "q-1": "I cannot tell.",
    }.get(slug, "[]")


def fake_results(reqs_by_id, slugs):
    return [llm.Result(id=propose.request_id(s), text=reply_for(s), usd=0.01, backend="batch",
                       model="claude-sonnet-5-5") for s in slugs if propose.request_id(s) in reqs_by_id]


def args(**kw):
    base = dict(run="r1", backend=None, model="sonnet", include_easy=False, include_people=False, limit=None,
                max_usd=6.0, dry_run=False, retry=False, wait=0, min_confidence=0.5)
    return SimpleNamespace(**{**base, **kw})


def test_dry_run_estimates_and_writes_nothing(vault, monkeypatch, capsys):
    monkeypatch.setattr(llm, "submit", lambda *a, **k: pytest.fail("dry run sends nothing"))
    before = tree(str(vault), skip="")
    assert propose.cmd_submit(args(dry_run=True)) == 0
    out = capsys.readouterr().out
    assert "4 subjects, 4 requests" in out and "via batch" in out and "worst case $" in out
    assert tree(str(vault), skip="") == before and not os.path.exists(vault / ".cache")


def test_submit_refuses_a_run_over_the_cap(vault, monkeypatch):
    monkeypatch.setattr(llm, "submit", lambda *a, **k: pytest.fail("over the cap: nothing is sent"))
    assert propose.cmd_submit(args(max_usd=0.0)) == 2
    assert not os.path.exists(vault / ".cache")


def test_submit_collect_review_batch(vault, monkeypatch, capsys):
    before = tree(str(vault))
    sent = {}
    monkeypatch.setattr(llm, "submit", lambda reqs, root=None: sent.update({r.id: r for r in reqs}) or "batch_1")
    assert propose.cmd_submit(args()) == 0
    assert len(sent) == 4 and all(r.model == "sonnet" and len(r.id) <= 64 for r in sent.values())
    assert propose.cmd_submit(args()) == 0 and len(sent) == 4                    # resumable: nothing new to send
    slugs = list(PAGES)
    monkeypatch.setattr(llm, "collect", lambda bid, wait_s=0, root=None: fake_results(sent, slugs))
    assert propose.cmd_collect(args()) == 0
    rows = [json.loads(l) for l in open(vault / ".cache" / propose.OUT_FILE)]
    assert {(r["from"], r["to"], r["kind"]) for r in rows} == {
        ("paper-a", "paper-b", "extends"), ("paper-a", "paper-b", "contradicts"),      # both subjects' contradicts → one row
        ("paper-a", "idea-x", "uses")}                                                  # the weak one is kept: confidence is data
    assert [r["confidence"] for r in rows if r["kind"] == "uses"] == [0.2]
    assert all(r["origin"] == "llm" and r["run"] == "r1" and r["model"] == "claude-sonnet-5-5" and r["at"] for r in rows)
    state = propose._load("r1")
    assert state["subjects"]["q-1"]["status"] == "rejected" and state["spent"] == pytest.approx(0.04)
    assert not any(str(r.get("reason", "")).startswith("confidence") for r in state["subjects"]["paper-a"]["rejected"])

    capsys.readouterr()
    assert propose.cmd_review(args()) == 0
    md = capsys.readouterr().out
    assert "## Paper A (`paper-a`)" in md and "**extends** → Paper B (`paper-b`) · confidence 0.90" in md
    assert "evidence: A extends B" in md and "note: A: x; B: not x" in md and "1 rejected." in md and "confidence 0.20" not in md   # review hides the weak row at 0.5
    assert propose.cmd_review(args(min_confidence=0.95)) == 0 and "Paper A" not in capsys.readouterr().out.split("\n", 3)[-1]

    state["batches"][0]["collected"] = False                                     # re-collect: the run's rows replace
    propose._save(state)
    with open(vault / ".cache" / propose.OUT_FILE, "a") as f:
        f.write(json.dumps({"from": "x", "to": "y", "kind": "uses", "run": "other"}) + "\n")
    propose.cmd_collect(args())
    rows = [json.loads(l) for l in open(vault / ".cache" / propose.OUT_FILE)]
    assert len(rows) == 4 and sum(r["run"] == "other" for r in rows) == 1       # this run's 3 (weak one included) + the other run's
    assert tree(str(vault)) == before                                            # nothing outside .cache changed


def test_direct_backend_and_easy_tier(vault, monkeypatch, capsys):
    seen = {}

    def fake_run(reqs, backend=None):
        seen["backend"] = backend
        seen["reqs"] = list(reqs)
        return [llm.Result(id=r.id, text='[{"to": "idea-x", "kind": "example-of", "confidence": 0.6}]',
                           model=llm.model_id(r.model), backend=backend) for r in reqs]
    monkeypatch.setattr(llm, "run", fake_run)
    monkeypatch.setattr(llm, "submit", lambda *a, **k: pytest.fail("api backend never batches"))
    monkeypatch.setenv(llm.ENV_BACKEND, "api")
    assert propose.cmd_submit(args(include_easy=True, run="easy")) == 0
    assert seen["backend"] == "api"
    easy = [r for r in seen["reqs"] if r.id == propose.request_id("blog-e")][0]
    assert easy.model == "haiku" and "- example-of:" in easy.prompt and "- extends:" not in easy.prompt
    rows = [json.loads(l) for l in open(vault / ".cache" / propose.OUT_FILE)]
    blog = [r for r in rows if r["from"] == "blog-e"]
    assert blog and blog[0]["tier"] == "low" and blog[0]["kind"] == "example-of"
    assert all(r.get("tier") != "low" for r in rows if r["from"] != "blog-e")
    assert propose._load("easy")["batches"][0]["collected"] is True


def test_direct_failure_is_saved_and_retryable(vault, monkeypatch):
    monkeypatch.setattr(llm, "run", lambda reqs, backend=None: (_ for _ in ()).throw(llm.LLMError("boom")))
    assert propose.cmd_submit(args(backend="api", run="f")) == 1
    state = propose._load("f")
    assert {t["status"] for t in state["subjects"].values()} == {"failed"}
    monkeypatch.setattr(llm, "run", lambda reqs, backend=None: [llm.Result(id=r.id, text="[]") for r in reqs])
    assert propose.cmd_submit(args(backend="api", run="f")) == 0
    assert {t["status"] for t in propose._load("f")["subjects"].values()} == {"failed"}       # not resent without --retry
    assert propose.cmd_submit(args(backend="api", run="f", retry=True)) == 0
    assert {t["status"] for t in propose._load("f")["subjects"].values()} == {"done"}


def test_a_numeric_slug_that_is_a_candidate_wins_over_the_index(vault):
    pages = pages_of(vault)
    pages["2"] = {**pages["paper-b"], "slug": "2"}
    acc, _ = propose.validate("paper-a", [{"to": "2", "kind": "uses", "confidence": 0.9}], ["idea-x", "2"], pages, KC)
    assert acc[0]["to"] == "2"


# --- confidence is data: weak rows are stored; a cutoff is asked for ------------------------------------------------
def old_run_state():
    """A run saved before weak rows were kept: one strong row, and rejected ones with three different reasons."""
    strong = {"from": "paper-a", "to": "paper-b", "kind": "extends", "note": "", "confidence": 0.9, "evidence": "e",
              "origin": "llm", "model": "m", "run": "old", "at": "t"}
    weak = {"from": "paper-a", "to": "idea-x", "kind": "uses", "note": "", "confidence": 0.4, "evidence": "e2",
            "reason": "confidence 0.4 < 0.5"}
    selfrel = {"from": "paper-a", "to": "paper-a", "kind": "uses", "note": "", "confidence": 0.9, "reason": "self-relation"}
    missing = {"from": "paper-a", "to": "idea-x", "kind": "extends", "note": "", "confidence": None,
               "reason": "confidence missing or outside 0..1"}
    return {"run": "old", "spent": 0.0, "batches": [], "subjects": {
        "paper-a": {"id": "s1", "status": "done", "easy": False, "model": "m", "proposals": [strong],
                    "rejected": [weak, selfrel, missing]}}}


def test_run_rows_promote_only_confidence_rejections_of_an_older_run(vault):
    rows = propose.run_rows(old_run_state())
    assert [(r["from"], r["to"], r["kind"], r["confidence"]) for r in rows] == [
        ("paper-a", "paper-b", "extends", 0.9), ("paper-a", "idea-x", "uses", 0.4)]      # not the self-relation, not the NaN
    assert all(r["origin"] == "llm" and r["run"] == "old" for r in rows)


def test_repack_rewrites_the_file_from_saved_state_and_is_idempotent(vault, capsys):
    propose._save(old_run_state())
    assert propose.cmd_repack(SimpleNamespace(run="old")) == 0
    first = open(vault / ".cache" / propose.OUT_FILE).read()
    assert [json.loads(l)["confidence"] for l in first.splitlines()] == [0.9, 0.4]
    assert propose.cmd_repack(SimpleNamespace(run="old")) == 0
    assert open(vault / ".cache" / propose.OUT_FILE).read() == first                 # same rows, no duplicates


def test_submit_keep_above_is_remembered_and_applied_when_the_reply_is_read(vault, monkeypatch):
    sent = {}
    monkeypatch.setattr(llm, "submit", lambda reqs, root=None: sent.update({r.id: r for r in reqs}) or "batch_1")
    assert propose.cmd_submit(args(keep_above=0.5)) == 0
    assert propose._load("r1")["keep_above"] == 0.5
    monkeypatch.setattr(llm, "collect", lambda bid, wait_s=0, root=None: fake_results(sent, list(PAGES)))
    assert propose.cmd_collect(args()) == 0
    rows = [json.loads(l) for l in open(vault / ".cache" / propose.OUT_FILE)]
    assert all(r["confidence"] >= 0.5 for r in rows)                                 # the 0.2 row was cut at creation
    assert any(str(r.get("reason", "")).startswith("confidence 0.2")
               for t in propose._load("r1")["subjects"].values() for r in t.get("rejected") or [])
