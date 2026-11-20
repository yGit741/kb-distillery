"""Server options: the default port falls through to the next free one; `--open-path` picks the page the tab opens;
KB_CHAT_SETTINGS points the chat settings at another file."""
import importlib
import socket

import pytest

from kb_distillery.server import __main__ as server_main


def _taken():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s, s.getsockname()[1]


def test_free_port_keeps_a_free_one():
    s, port = _taken()
    s.close()
    assert server_main.free_port("127.0.0.1", port, tries=1) == port


def test_free_port_skips_a_taken_one(capsys):
    s, port = _taken()
    try:
        got = server_main.free_port("127.0.0.1", port, tries=5)
    finally:
        s.close()
    assert port < got < port + 5
    assert f"port {port} is in use" in capsys.readouterr().out


def test_free_port_gives_up_with_a_clear_message():
    s, port = _taken()
    try:
        with pytest.raises(SystemExit, match="all in use; pass --port"):
            server_main.free_port("127.0.0.1", port, tries=1)
    finally:
        s.close()


def _run_main(monkeypatch, argv):
    import uvicorn

    from kb_distillery.graph import cache
    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw))
    monkeypatch.setattr(cache, "start_refresher", lambda: None)
    monkeypatch.setattr(server_main.webbrowser, "open", lambda url: seen.update(opened=url))
    monkeypatch.setattr(server_main, "free_port", lambda host, wanted: 8799)
    assert server_main.main(["--no-build", *argv]) == 0
    return seen


def test_main_without_port_takes_the_free_one_and_open_path(monkeypatch):
    seen = _run_main(monkeypatch, ["--open-path", "/app/graph"])
    assert seen["port"] == 8799
    assert seen["opened"] == "http://127.0.0.1:8799/app/graph"


def test_main_with_port_uses_it_as_is(monkeypatch):
    seen = _run_main(monkeypatch, ["--port", "9001"])
    assert seen["port"] == 9001
    assert seen["opened"] == "http://127.0.0.1:9001/app/start"


def test_open_path_must_be_absolute(monkeypatch):
    with pytest.raises(SystemExit):
        _run_main(monkeypatch, ["--open-path", "app/graph"])


def test_chat_settings_file_from_env(monkeypatch, tmp_path):
    from kb_distillery.services import chat
    target = tmp_path / "chat.json"
    monkeypatch.setenv("KB_CHAT_SETTINGS", str(target))
    try:
        assert importlib.reload(chat).SETTINGS_FILE == str(target)
    finally:
        monkeypatch.delenv("KB_CHAT_SETTINGS")
        importlib.reload(chat)
