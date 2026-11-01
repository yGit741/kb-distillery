"""config/userdir.py: the one place that knows ~/.config/kb-distillery. Every test points HOME at a temp folder; the real
~/.config is never read or written. The engine never moves the old ~/.config/thesis-kb for the user: it says how."""
import os
import subprocess
import sys

import pytest

from kb_distillery.config import userdir

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_paths_live_under_the_new_folder(home):
    assert userdir.config_dir() == str(home / ".config" / "kb-distillery")
    assert userdir.path("anthropic_key") == str(home / ".config" / "kb-distillery" / "anthropic_key")
    assert userdir.path("keys", "s2") == str(home / ".config" / "kb-distillery" / "keys" / "s2")
    assert userdir.legacy_dir() == str(home / ".config" / "thesis-kb")
    assert userdir.display("anthropic_key") == "~/.config/kb-distillery/anthropic_key"


def test_nothing_to_migrate_without_the_old_folder_or_with_the_new_one(home):
    assert not userdir.migration_needed() and userdir.check() is None
    (home / ".config" / "kb-distillery").mkdir(parents=True)
    assert not userdir.migration_needed() and userdir.check() is None
    (home / ".config" / "thesis-kb").mkdir()                              # both exist: the user already chose
    assert not userdir.migration_needed() and userdir.check() is None


def test_only_the_old_folder_gives_the_exact_mv_and_moves_nothing(home):
    old = home / ".config" / "thesis-kb"
    (old / "keys").mkdir(parents=True)
    (old / "anthropic_key").write_text("sk-test\n")
    assert userdir.migration_needed()
    msg = userdir.check()
    assert f"mv {old} {home / '.config' / 'kb-distillery'}" in msg
    assert userdir.migration_command() == f"mv {old} {home / '.config' / 'kb-distillery'}"
    assert (old / "anthropic_key").read_text() == "sk-test\n"
    assert not (home / ".config" / "kb-distillery").exists()


def test_the_mv_quotes_a_home_with_spaces(tmp_path, monkeypatch):
    spaced = tmp_path / "my home"
    (spaced / ".config" / "thesis-kb").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(spaced))
    assert userdir.migration_command().startswith("mv '")


def test_keychain_names_try_the_new_service_first_then_the_old_one():
    assert userdir.keychain_services("kb-distillery-gmail") == ["kb-distillery-gmail", "thesis-kb-gmail"]
    assert userdir.keychain_services("kb-distillery-gmail-imap") == ["kb-distillery-gmail-imap", "thesis-kb-gmail-imap"]
    assert userdir.keychain_services("something-else") == ["something-else"]


def test_consumers_take_the_new_folder_from_home(tmp_path):
    code = ("from kb_distillery import llm; from kb_distillery.services import chat; from kb_distillery.ingest import mail; "
            "print(llm.KEY_FILE); print(chat.KEY_FILE); print(chat.KEYS_DIR); print(chat.SETTINGS_FILE); print(mail.KEYCHAIN_SERVICE)")
    env = {**os.environ, "HOME": str(tmp_path), "PYTHONPATH": SRC, "KB_APP_CONFIG": "/nonexistent/app.toml"}
    for k in ("KB", "KB_ROOT"):
        env.pop(k, None)
    cp = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(tmp_path), check=False)
    assert cp.returncode == 0, cp.stderr[-500:]
    base = str(tmp_path / ".config" / "kb-distillery")
    assert cp.stdout.split() == [f"{base}/anthropic_key", f"{base}/anthropic_key", f"{base}/keys", f"{base}/chat.json",
                                 "kb-distillery-gmail-imap"]


def test_citations_read_the_s2_key_from_the_new_folder(home, monkeypatch):
    from kb_distillery.search import citations
    monkeypatch.delenv("S2_API_KEY", raising=False)
    (home / ".config" / "kb-distillery" / "keys").mkdir(parents=True)
    (home / ".config" / "kb-distillery" / "keys" / "s2").write_text("s2-secret\n")
    assert citations._headers()["x-api-key"] == "s2-secret"
