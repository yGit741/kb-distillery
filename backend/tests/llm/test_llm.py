"""kb.llm: one door, three backends. No network and no CLI: _http, _cli and _sleep are replaced per test."""
import json
import os
import re
import subprocess
import threading
import types

import pytest

from kb import llm

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src", "kb")


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv(llm.ENV_BACKEND, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "_sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(llm, "batch_dir", lambda: str(tmp_path / "batches"))
    monkeypatch.setattr(llm, "_http", _no_network)
    monkeypatch.setattr(llm, "_cli", _no_cli)
    sleeps.clear()


sleeps = []


def _no_network(*a, **k):
    raise AssertionError("unexpected network call")


def _no_cli(*a, **k):
    raise AssertionError("unexpected claude -p call")


def message(text="hi", stop="end_turn", usage=None, **extra):
    return {"type": "message", "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}],
            "stop_reason": stop, "usage": usage or {"input_tokens": 1000, "output_tokens": 200}, **extra}


class FakeAPI:
    """Records calls; `script` maps (method, path suffix) → list of responses (bytes, dict or HTTPFail), popped in order."""

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, method, url, key, body=None, timeout=300):
        with self.lock:
            self.calls.append({"method": method, "url": url, "key": key, "body": body})
            for (m, suffix), queue in self.script.items():
                if m == method and url.endswith(suffix) and queue:
                    r = queue.pop(0)
                    break
            else:
                raise AssertionError(f"unscripted {method} {url}")
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, bytes) else json.dumps(r).encode()


# --- resolution ----------------------------------------------------------------------------------------
def test_backend_precedence(monkeypatch):
    assert llm.resolve_backend() == llm.DEFAULT_BACKEND == "subscription"
    monkeypatch.setenv(llm.ENV_BACKEND, "Batch ")
    assert llm.resolve_backend() == "batch"
    assert llm.resolve_backend("api") == "api"          # explicit argument beats the env


@pytest.mark.parametrize("bad", ["claude", "API2", "sub"])
def test_unknown_backend_raises(bad, monkeypatch):
    with pytest.raises(llm.LLMError):
        llm.resolve_backend(bad)
    monkeypatch.setenv(llm.ENV_BACKEND, bad)
    with pytest.raises(llm.LLMError):
        llm.run(["x"])


def test_models_and_unknown_model():
    assert llm.model_id("haiku") == "claude-haiku-5-5"
    assert llm.model_id("claude-opus-5-5") == "claude-opus-5-5"
    with pytest.raises(llm.LLMError):
        llm.model_id("gpt-5")
    with pytest.raises(llm.LLMError):            # caught before any backend is touched
        llm.run([llm.Request("x", model="haiku-4")], backend="api")


def test_cost_exact():
    u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
         "cache_creation_input_tokens": 1_000_000}
    assert llm.cost("haiku", u) == pytest.approx(0.10 + 0.50 + 0.01 + 0.125)
    assert llm.cost("sonnet", u, batch=True) == pytest.approx((2 + 10 + 0.2 + 2.5) / 2)
    assert llm.cost("opus", {}) == 0


@pytest.mark.parametrize("ids", [["a", "a"], ["has space"], ["x" * 65], ["ok", "bad/slash"]])
def test_bad_ids_rejected_before_sending(ids):
    with pytest.raises(llm.LLMError):
        llm.submit([llm.Request("p", id=i) for i in ids])


def test_ids_filled_by_index_and_inputs_not_mutated():
    src = [llm.Request("a"), "b", llm.Request("c", id="mine")]
    out = llm.normalize(src)
    assert [r.id for r in out] == ["r0", "r1", "mine"]
    assert src[0].id == ""


def test_empty_run_touches_nothing():
    assert llm.run([], backend="batch") == []


# --- subscription ----------------------------------------------------------------------------------------
def cli_ok(result="hello", cost=0.0012, code=0, **extra):
    out = {"type": "result", "result": result, "total_cost_usd": cost, "is_error": False, **extra}
    return subprocess.CompletedProcess([], code, stdout=json.dumps(out), stderr="")


def test_subscription_command_env_and_cwd(monkeypatch):
    seen = {}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-not-leak")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")

    def fake(cmd, cwd, env, timeout):
        seen.update(cmd=cmd, cwd=cwd, env=env, files=os.listdir(cwd))
        return cli_ok()
    monkeypatch.setattr(llm, "_cli", fake)
    r = llm.ask("what?", system="be brief", model="sonnet", effort="medium")
    assert r.ok and r.text == "hello" and r.backend == "subscription" and r.usd == 0.0012
    cmd = seen["cmd"]
    assert cmd[:2] == ["claude", "-p"] and cmd[2] == "be brief\n\nwhat?"
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"
    assert cmd[cmd.index("--effort") + 1] == "medium"
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--no-session-persistence" in cmd and "--strict-mcp-config" in cmd
    assert not set(llm._SCRUBBED) & set(seen["env"])       # runs on the login, never the key
    assert seen["files"] == [] and not os.path.exists(seen["cwd"])


@pytest.mark.parametrize("proc,err", [
    (subprocess.CompletedProcess([], 1, stdout="", stderr="boom"), "claude exited 1: boom"),
    (subprocess.CompletedProcess([], 0, stdout="not json", stderr=""), "Expecting value"),
    (cli_ok(code=1), "claude exited 1"),
    (subprocess.CompletedProcess([], 0, stdout=json.dumps({"result": "x", "is_error": True}), stderr=""),
     "claude exited 0"),
    (cli_ok(result=""), "empty result"),
])
def test_subscription_failures_retry_then_report(monkeypatch, proc, err):
    n = []
    monkeypatch.setattr(llm, "_cli", lambda *a: (n.append(1), proc)[1])
    r = llm.ask("q")
    assert not r.ok and err in r.error and r.text == ""
    assert len(n) == 3 and sleeps == [5, 10]


def test_subscription_timeout_then_success(monkeypatch):
    seq = [subprocess.TimeoutExpired("claude", 600), cli_ok("late")]

    def fake(*a):
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(llm, "_cli", fake)
    r = llm.ask("q")
    assert r.ok and r.text == "late" and sleeps == [5]


def test_subscription_parallel_keeps_order(monkeypatch):
    import random
    import time as _t

    def fake(cmd, cwd, env, timeout):
        _t.sleep(random.random() / 50)
        return cli_ok(result="ans:" + cmd[2])
    monkeypatch.setattr(llm, "_cli", fake)
    res = llm.run([f"p{i}" for i in range(20)], workers=8)
    assert [r.text for r in res] == [f"ans:p{i}" for i in range(20)]
    assert [r.id for r in res] == [f"r{i}" for i in range(20)]


# --- api -------------------------------------------------------------------------------------------------
def test_api_request_shape_and_cost(monkeypatch):
    api = FakeAPI({("POST", "/v1/messages"): [message("answer")]})
    monkeypatch.setattr(llm, "_http", api)
    r = llm.ask("q", backend="api", system="sys", max_tokens=50)
    assert r.ok and r.text == "answer" and r.backend == "api" and r.model == "claude-haiku-5-5"
    assert r.usd == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1e6)
    c = api.calls[0]
    assert c["url"] == "https://api.anthropic.com/v1/messages" and c["key"] == "sk-test"
    assert c["body"] == {"model": "claude-haiku-5-5", "max_tokens": 50, "system": "sys",
                         "messages": [{"role": "user", "content": "q"}], "output_config": {"effort": "low"}}


def test_api_no_system_field_when_empty(monkeypatch):
    api = FakeAPI({("POST", "/v1/messages"): [message()]})
    monkeypatch.setattr(llm, "_http", api)
    llm.ask("q", backend="api")
    assert "system" not in api.calls[0]["body"]


@pytest.mark.parametrize("status", [429, 529, 500, 0])
def test_api_retries_transient(monkeypatch, status):
    api = FakeAPI({("POST", "/v1/messages"): [llm.HTTPFail(status, "busy"), llm.HTTPFail(status, "busy"),
                                              message("ok")]})
    monkeypatch.setattr(llm, "_http", api)
    r = llm.ask("q", backend="api")
    assert r.ok and r.text == "ok" and len(api.calls) == 3 and sleeps == [2, 4]


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_api_no_retry_on_client_error(monkeypatch, status):
    api = FakeAPI({("POST", "/v1/messages"): [llm.HTTPFail(status, "nope")]})
    monkeypatch.setattr(llm, "_http", api)
    r = llm.ask("q", backend="api")
    assert not r.ok and f"API {status}: nope" in r.error and len(api.calls) == 1 and sleeps == []


def test_api_gives_up_after_retries(monkeypatch):
    api = FakeAPI({("POST", "/v1/messages"): [llm.HTTPFail(529, "overloaded")] * 4})
    monkeypatch.setattr(llm, "_http", api)
    r = llm.ask("q", backend="api")
    assert "API 529" in r.error and len(api.calls) == 4


def test_api_missing_key_fails_without_network(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setattr(llm, "KEY_FILE", str(tmp_path / "none"))
    r = llm.ask("q", backend="api")
    assert not r.ok and "no API key" in r.error


def test_api_key_file_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    (tmp_path / "k").write_text("  sk-from-file\n")
    monkeypatch.setattr(llm, "KEY_FILE", str(tmp_path / "k"))
    api = FakeAPI({("POST", "/v1/messages"): [message()]})
    monkeypatch.setattr(llm, "_http", api)
    assert llm.ask("q", backend="api").ok and api.calls[0]["key"] == "sk-from-file"


@pytest.mark.parametrize("msg,err,text", [
    (message("", stop="refusal", stop_details={"category": "cyber"}), "refused: cyber", ""),
    (message("half", stop="max_tokens"), "cut at max_tokens", "half"),
    (message(""), "empty result", ""),
])
def test_api_stop_reasons(monkeypatch, msg, err, text):
    monkeypatch.setattr(llm, "_http", FakeAPI({("POST", "/v1/messages"): [msg]}))
    r = llm.ask("q", backend="api")
    assert not r.ok and err in r.error and r.text == text and r.usd > 0   # tokens are still billed


def test_api_garbage_body(monkeypatch):
    monkeypatch.setattr(llm, "_http", FakeAPI({("POST", "/v1/messages"): [b"<html>"]}))
    assert not llm.ask("q", backend="api").ok


# --- batch -----------------------------------------------------------------------------------------------
def batch_obj(bid, state, url=None):
    return {"id": bid, "type": "message_batch", "processing_status": state,
            "results_url": url, "request_counts": {}}


def jsonl(*rows):
    return "\n".join(json.dumps(r) for r in rows).encode() + b"\n"


def ok_row(cid, text, usage=None):
    return {"custom_id": cid, "result": {"type": "succeeded", "message": message(text, usage=usage)}}


def test_batch_end_to_end_out_of_order(monkeypatch):
    url = "https://api.anthropic.com/v1/messages/batches/b1/results"
    api = FakeAPI({
        ("POST", "/v1/messages/batches"): [{"id": "b1", "processing_status": "in_progress"}],
        ("GET", "/v1/messages/batches/b1"): [batch_obj("b1", "in_progress"), batch_obj("b1", "in_progress"),
                                             batch_obj("b1", "ended", url)],
        ("GET", "/results"): [jsonl(
            ok_row("c", "C"),
            {"custom_id": "b", "result": {"type": "errored",
                                           "error": {"type": "error", "error": {"message": "bad param"}}}},
            {"custom_id": "e", "result": {"type": "expired"}},
            ok_row("a", "A"),
        )],
    })
    monkeypatch.setattr(llm, "_http", api)
    reqs = [llm.Request(f"prompt {i}", id=i, model="sonnet" if i == "c" else "haiku") for i in "abcde"]
    res = llm.run(reqs, backend="batch", poll_every=7)

    assert [r.id for r in res] == list("abcde")
    assert [r.text for r in res] == ["A", "", "C", "", ""]
    assert res[0].ok and res[2].ok
    assert res[1].error == "errored: bad param"
    assert res[3].error == "missing from batch results"
    assert res[4].error == "expired"
    assert res[0].usd == pytest.approx((1000 * 0.10 + 200 * 0.50) / 1e6 / 2)      # half price
    assert res[2].model == "claude-sonnet-5-5"
    assert res[2].usd == pytest.approx((1000 * 2 + 200 * 10) / 1e6 / 2)
    assert sleeps == [7, 7]
    sent = api.calls[0]["body"]["requests"]
    assert [s["custom_id"] for s in sent] == list("abcde")
    assert sent[2]["params"]["model"] == "claude-sonnet-5-5"
    assert sent[0]["params"]["max_tokens"] == llm.Request("x").max_tokens == 8192


def test_batch_submit_then_collect_elsewhere(monkeypatch, tmp_path):
    """submit in one process, collect in another by id alone: the manifest restores order and models."""
    api = FakeAPI({("POST", "/v1/messages/batches"): [{"id": "msgbatch_9"}]})
    monkeypatch.setattr(llm, "_http", api)
    bid = llm.submit([llm.Request("x", id="z1"), llm.Request("y", id="z2", model="opus")])
    m = json.loads((tmp_path / "batches" / f"{bid}.json").read_text())
    assert [q["id"] for q in m["requests"]] == ["z1", "z2"] and m["requests"][1]["model"] == "claude-opus-5-5"

    api2 = FakeAPI({("GET", "/v1/messages/batches/msgbatch_9"): [batch_obj(bid, "ended", None)],
                    ("GET", "/v1/messages/batches/msgbatch_9/results"): [jsonl(ok_row("z2", "two"),
                                                                               ok_row("z1", "one"))]})
    monkeypatch.setattr(llm, "_http", api2)
    res = llm.collect(bid)
    assert [(r.id, r.text, r.model) for r in res] == [("z1", "one", "claude-haiku-5-5"),
                                                       ("z2", "two", "claude-opus-5-5")]
    assert sleeps == []


def test_batch_collect_gives_up_without_hanging(monkeypatch):
    api = FakeAPI({("POST", "/v1/messages/batches"): [{"id": "slow"}],
                   ("GET", "/v1/messages/batches/slow"): [batch_obj("slow", "in_progress")] * 10})
    monkeypatch.setattr(llm, "_http", api)
    clock = types.SimpleNamespace(t=0.0)
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock.t)
    monkeypatch.setattr(llm, "_sleep", lambda s: setattr(clock, "t", clock.t + s) or sleeps.append(s))
    res = llm.run(["a", "b"], backend="batch", poll_every=10, wait_s=35)
    assert all("still in_progress" in r.error and "collect it later" in r.error for r in res)
    assert sleeps == [10, 10, 10]


def test_batch_submit_failure_raises_and_writes_no_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_http", FakeAPI({("POST", "/v1/messages/batches"): [llm.HTTPFail(400, "too big")]}))
    with pytest.raises(llm.HTTPFail):
        llm.submit(["a"])
    assert not (tmp_path / "batches").exists()


def test_batch_size_limit(monkeypatch):
    monkeypatch.setattr(llm, "BATCH_MAX", 3)
    with pytest.raises(llm.LLMError):
        llm.submit(["a", "b", "c", "d"])


def test_ask_with_batch_backend(monkeypatch):
    api = FakeAPI({("POST", "/v1/messages/batches"): [{"id": "one"}],
                   ("GET", "/v1/messages/batches/one"): [batch_obj("one", "ended")],
                   ("GET", "/v1/messages/batches/one/results"): [jsonl(ok_row("r0", "solo"))]})
    monkeypatch.setattr(llm, "_http", api)
    r = llm.ask("q", backend="batch")
    assert r.ok and r.text == "solo" and r.backend == "batch"


def test_env_switches_every_caller(monkeypatch):
    monkeypatch.setenv(llm.ENV_BACKEND, "api")
    monkeypatch.setattr(llm, "_http", FakeAPI({("POST", "/v1/messages"): [message("via env")]}))
    assert llm.ask("q").backend == "api"


# --- images ----------------------------------------------------------------------------------------------
JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


def test_api_image_blocks_before_text(monkeypatch, tmp_path):
    import base64
    img = tmp_path / "f-00012.jpg"
    img.write_bytes(JPEG)
    png = tmp_path / "b.PNG"
    png.write_bytes(b"\x89PNG")
    api = FakeAPI({("POST", "/v1/messages"): [message("$$x$$")]})
    monkeypatch.setattr(llm, "_http", api)
    r = llm.ask("transcribe", backend="api", images=[str(img), str(png)])
    assert r.ok
    content = api.calls[0]["body"]["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "image", "text"] and content[2]["text"] == "transcribe"
    assert content[0]["source"] == {"type": "base64", "media_type": "image/jpeg",
                                    "data": base64.b64encode(JPEG).decode()}
    assert content[1]["source"]["media_type"] == "image/png"


def test_subscription_image_uses_read_only_from_image_dir(monkeypatch, tmp_path):
    img = tmp_path / "frames" / "f.jpg"
    img.parent.mkdir()
    img.write_bytes(JPEG)
    seen = {}
    monkeypatch.setattr(llm, "_cli", lambda cmd, cwd, env, timeout: (seen.update(cmd=cmd, cwd=cwd), cli_ok("ok"))[1])
    assert llm.ask("transcribe", images=[str(img)]).ok
    cmd = seen["cmd"]
    assert cmd[cmd.index("--tools") + 1] == "Read" and cmd[cmd.index("--allowedTools") + 1] == "Read"
    assert seen["cwd"] == str(img.parent)
    assert cmd[2].startswith(f"Read the image file {img} first.") and cmd[2].endswith("transcribe")


def test_text_only_subscription_keeps_no_tools(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm, "_cli", lambda cmd, cwd, env, timeout: (seen.update(cmd=cmd), cli_ok())[1])
    llm.ask("q")
    assert "--allowedTools" not in seen["cmd"] and seen["cmd"][seen["cmd"].index("--tools") + 1] == ""


@pytest.mark.parametrize("name,write,err", [("x.bmp", True, "images must be"), ("gone.jpg", False, "no such image")])
def test_bad_images_rejected_before_any_call(tmp_path, name, write, err):
    p = tmp_path / name
    if write:
        p.write_bytes(b"x")
    with pytest.raises(llm.LLMError, match=err):
        llm.run([llm.Request("q", images=[str(p)])], backend="batch")


def test_batch_carries_images(monkeypatch, tmp_path):
    img = tmp_path / "f.jpg"
    img.write_bytes(JPEG)
    api = FakeAPI({("POST", "/v1/messages/batches"): [{"id": "im"}]})
    monkeypatch.setattr(llm, "_http", api)
    llm.submit([llm.Request("q", images=[str(img)])])
    content = api.calls[0]["body"]["requests"][0]["params"]["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[-1] == {"type": "text", "text": "q"}


def test_fable_priced():
    assert llm.model_id("fable") == "claude-fable-5-1"
    assert llm.cost("fable", {"input_tokens": 1_000_000, "output_tokens": 100_000}) == pytest.approx(15.0)


@pytest.mark.parametrize("text,want", [
    ('{"a": 1}', {"a": 1}),
    ('Sure!\n```json\n{"a": {"b": [1, 2]}}\n```\nDone.', {"a": {"b": [1, 2]}}),
    ("no json here", None),
    ("{broken", None),
    ("[1, 2]", None),
    ("", None),
    (None, None),
])
def test_json_object(text, want):
    assert llm.json_object(text) == want


def test_tls_needs_no_knowledge_base():
    """Regression: TLS came from kb.services.chat, which loads the vault on import; with an unknown KB the
    fallback was Python's bare CA bundle and every call behind the proxy failed CERTIFICATE_VERIFY_FAILED."""
    import sys
    env = {**os.environ, "KB": "no-such-kb", "PYTHONPATH": os.path.join(SRC, "..")}
    env.pop("KB_ROOT", None)
    cp = subprocess.run([sys.executable, "-c", "from kb import llm; print(type(llm._ssl()).__name__)"],
                        env=env, capture_output=True, text=True, timeout=60)
    assert cp.stdout.strip() == "SSLContext", cp.stderr[-500:]


# --- cli -------------------------------------------------------------------------------------------------
def test_cli_ask_exit_codes(monkeypatch, capsys):
    from kb.llm.__main__ import main
    monkeypatch.setattr(llm, "_http", FakeAPI({("POST", "/v1/messages"): [message("yo"), llm.HTTPFail(400, "x")]}))
    assert main(["ask", "q", "--backend", "api"]) == 0
    assert json.loads(capsys.readouterr().out)["text"] == "yo"
    assert main(["ask", "q", "--backend", "api"]) == 1


def test_cli_submit_jsonl(monkeypatch, tmp_path, capsys):
    from kb.llm.__main__ import main
    f = tmp_path / "in.jsonl"
    f.write_text('{"prompt": "a", "id": "x1"}\nplain prompt line\n\n')
    api = FakeAPI({("POST", "/v1/messages/batches"): [{"id": "bb"}]})
    monkeypatch.setattr(llm, "_http", api)
    assert main(["submit", str(f)]) == 0
    assert capsys.readouterr().out.strip() == "bb"
    assert [r["custom_id"] for r in api.calls[0]["body"]["requests"]] == ["x1", "r1"]


# --- the rule: one door ----------------------------------------------------------------------------------
# Callers that predate kb.llm and still call Claude directly (summaries, easy-digest, extract and video frames
# have moved). The list may only shrink: a new direct `claude -p` or api.anthropic.com call anywhere else fails.
LEGACY = {
    "metrics/judge.py",
    "metrics/golden.py",
    "services/chat.py",           # dashboard chat (interactive, streaming)
    "services/chat_agent.py",     # dashboard research agent (Agent SDK; has its own subscription/api_key switch)
}
DIRECT = re.compile(r'"claude",\s*"-p"|api\.anthropic\.com|import anthropic|from anthropic|claude_agent_sdk')


def test_no_llm_calls_outside_kb_llm():
    hits = set()
    for root, _, files in os.walk(SRC):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, SRC).replace(os.sep, "/")
            if rel.startswith("llm/"):
                continue
            with open(path, encoding="utf-8") as f:
                if DIRECT.search(f.read()):
                    hits.add(rel)
    assert hits - LEGACY == set(), "call Claude through kb.llm, not directly"
    assert LEGACY - hits == set(), "a legacy caller moved to kb.llm: drop it from LEGACY"
