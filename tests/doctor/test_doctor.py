"""kbd doctor and kb_distillery.llm.availability: every check is a small function, tested with fakes. No network, no LLM."""
import json
import os
import types

import pytest

from kb_distillery import doctor, kbconfig, llm
from kb_distillery.doctor import FAIL, INFO, PASS, WARN
from kb_distillery.storage.base import AuthStatus


def status(checks, name):
    return next(c for c in checks if c.name == name).status


# --- llm.availability ------------------------------------------------------------------------------------
@pytest.fixture
def no_keys(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "KEY_FILE", str(tmp_path / "nokey"))


def test_availability_nothing(monkeypatch, no_keys):
    monkeypatch.setattr(llm, "_which", lambda n: None)
    a = llm.availability()
    assert set(a) == set(llm.BACKENDS)
    for v in a.values():
        assert v["ok"] is False and v["why"] and v["fix"]


def test_availability_subscription_logged_in(monkeypatch, no_keys):
    monkeypatch.setattr(llm, "_which", lambda n: "/bin/claude")
    calls = []
    monkeypatch.setattr(llm, "_probe", lambda cmd, timeout=8: calls.append(cmd) or (0, '\x1b]111\x07{"loggedIn": true, "authMethod": "claude.ai"}'))
    a = llm.availability()
    assert a["subscription"]["ok"] and not a["api"]["ok"] and not a["batch"]["ok"]
    assert calls == [["claude", "auth", "status"]]            # only the status query, never a prompt


def test_availability_subscription_not_logged_in_or_garbled(monkeypatch, no_keys):
    monkeypatch.setattr(llm, "_which", lambda n: "/bin/claude")
    monkeypatch.setattr(llm, "_probe", lambda cmd, timeout=8: (0, '{"loggedIn": false}'))
    assert not llm.availability()["subscription"]["ok"]
    monkeypatch.setattr(llm, "_probe", lambda cmd, timeout=8: (1, "oops"))
    assert "login" in llm.availability()["subscription"]["fix"]


def test_availability_key_from_env_and_file(monkeypatch, no_keys, tmp_path):
    monkeypatch.setattr(llm, "_which", lambda n: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    a = llm.availability()
    assert a["api"]["ok"] and a["batch"]["ok"] and "sk-secret" not in json.dumps(a)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    key = tmp_path / "key"
    key.write_text("sk-file\n")
    monkeypatch.setattr(llm, "KEY_FILE", str(key))
    a = llm.availability()
    assert a["api"]["ok"] and str(key) in a["api"]["why"] and "sk-file" not in json.dumps(a)


# --- environment checks ----------------------------------------------------------------------------------
def test_python():
    assert status(doctor.check_python((3, 9, 0), "/x", {}), "python") == FAIL
    out = doctor.check_python((3, 12, 1), "/p/.pixi/envs/default", {})
    assert [c.status for c in out] == [PASS, PASS]
    assert status(doctor.check_python((3, 12, 1), "/usr", {}), "pixi env") == WARN


def test_node():
    assert doctor.check_node(lambda n: "/bin/node").status == PASS
    c = doctor.check_node(lambda n: None)
    assert c.status == WARN and "pixi install" in c.fix


def test_git():
    assert doctor.check_git(lambda n: None)[0].status == FAIL
    both = doctor.check_git(lambda n: "/bin/git", lambda k: "x")
    assert status(both, "git identity") == PASS
    none = doctor.check_git(lambda n: "/bin/git", lambda k: "")
    assert status(none, "git identity") == WARN and "git config" in none[1].fix


# --- kb checks -------------------------------------------------------------------------------------------
def test_kb_found():
    assert doctor.check_kb_found({}, "/b", None).status == WARN
    assert "kbd init" in doctor.check_kb_found({}, "/b", None).fix
    assert doctor.check_kb_found({"a": "/a"}, "/b", None).status == PASS
    assert doctor.check_kb_found({"a": "/a", "b": "/b"}, "/b", None).status == WARN
    assert doctor.check_kb_found({"a": "/a", "b": "/b"}, "/b", "a").status == PASS


def test_kb_config_errors_name_their_fix():
    def boom(msg):
        def loader(ref):
            raise kbconfig.KbConfigError(msg)
        return loader
    c, cfg = doctor.check_kb_config("x", boom("kb.toml: schema_version 1.3 but this explorer speaks 1.7"))
    assert c.status == FAIL and cfg is None and "migrate" in c.fix
    c, _ = doctor.check_kb_config("x", boom("[kb] kit = 'q' is not a known kit"))
    assert c.status == FAIL and "kit" in c.fix
    c, _ = doctor.check_kb_config("x", boom("no knowledge base 'x'"))
    assert c.status == FAIL


def test_kb_config_ok_and_layout(tmp_path):
    root = tmp_path / "k"
    root.mkdir()
    cfg = types.SimpleNamespace(id="k", schema_version=(1, 5), kit="base", root=str(root), git_root=None)
    c, got = doctor.check_kb_config("k", lambda ref: cfg)
    assert c.status == PASS and got is cfg and "base" in c.detail
    assert doctor.check_kb_layout(cfg).status == WARN            # no wiki/ meta/
    for d in ("wiki", "meta"):
        (root / d).mkdir()
    assert doctor.check_kb_layout(cfg).status == INFO            # not a git repo
    cfg.git_root = str(root)
    assert doctor.check_kb_layout(cfg).status == PASS


def test_storage():
    ok = types.SimpleNamespace(auth=lambda: AuthStatus(True))
    bad = types.SimpleNamespace(auth=lambda: AuthStatus(False, "token expired"))
    assert doctor.check_storage(None, lambda cfg: ok).status == PASS
    c = doctor.check_storage(None, lambda cfg: bad)
    assert c.status == WARN and "token expired" in c.detail

    def broken(cfg):
        raise RuntimeError("no connector")
    assert doctor.check_storage(None, broken).status == FAIL


def test_publisher():
    from kb_distillery.publish.null import NullPublisher
    assert doctor.check_publisher(None, lambda cfg: NullPublisher()).status == INFO
    assert doctor.check_publisher(None, lambda cfg: NullPublisher(reason="no publisher 'x'")).status == WARN
    assert doctor.check_publisher(None, lambda cfg: types.SimpleNamespace()).status == PASS


def test_llm_none_is_info_only():
    off = {b: {"ok": False, "why": "no", "fix": "do x"} for b in llm.BACKENDS}
    out = doctor.check_llm(off)
    assert {c.status for c in out} == {INFO}
    assert doctor.check_llm({**off, "api": {"ok": True, "why": "key", "fix": ""}})[1].status == PASS


def test_frontend(tmp_path):
    fe = str(tmp_path)
    assert doctor.check_frontend(fe, False, os.path.join(fe, "dist")).status == WARN
    first = doctor.check_frontend(fe, True, os.path.join(fe, "dist"))
    assert first.status == INFO and "first launch" in first.fix           # a fresh clone is not a problem: launch builds it
    os.makedirs(tmp_path / "node_modules")
    assert doctor.check_frontend(fe, True, os.path.join(fe, "dist")).status == PASS
    os.makedirs(tmp_path / "dist")
    (tmp_path / "dist" / "index.html").write_text("x")
    assert doctor.check_frontend(fe, False, os.path.join(fe, "dist")).status == PASS


# --- whole run -------------------------------------------------------------------------------------------
def test_exit_code_and_render():
    ok = [doctor.Check("a", PASS, "fine"), doctor.Check("b", INFO, "meh", "later")]
    assert doctor.exit_code(ok) == 0
    assert doctor.exit_code([*ok, doctor.Check("c", FAIL, "bad", "fix it")]) == 1
    text = doctor.render([doctor.Check("c", FAIL, "bad", "fix it")])
    assert "FAIL" in text and "fix: fix it" in text


def test_main_json_on_empty_bases_dir(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KB_BASES_DIR", str(tmp_path / "kbs"))
    for k in ("KB", "KB_ROOT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "_which", lambda n: None)
    rc = doctor.main(["--json"])
    rows = json.loads(capsys.readouterr().out)
    assert rc in (0, 1) and any(r["name"] == "knowledge base" and r["status"] == WARN for r in rows)


# --- config folder (~/.config/kb-distillery) -------------------------------------------------------------
def test_config_folder_only_the_old_one_is_a_fail_with_the_exact_mv(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert doctor.check_config_dir().status == INFO                      # nothing yet: fine
    old = tmp_path / ".config" / "thesis-kb"
    old.mkdir(parents=True)
    c = doctor.check_config_dir()
    assert c.status == FAIL and c.fix == f"mv {old} {tmp_path / '.config' / 'kb-distillery'}"
    assert old.is_dir() and not (tmp_path / ".config" / "kb-distillery").exists()   # reported, never moved
    (tmp_path / ".config" / "kb-distillery").mkdir()
    assert doctor.check_config_dir().status == PASS
