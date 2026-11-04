"""distill kb inbox: pick up the site's pending uploads and import them. The site is a fake behind `Client.request`;
temp dirs only; never ~/knowledge, never the network."""
import io
import json
import os
import zipfile

import pytest

from kb_distillery import inbox, llm
from kb_distillery.cli import tree
from kb_distillery.config import kb as kbconfig

TOKEN = "t0ken-for-tests-only"
PAGE = "---\ntype: idea\nlayer: concept\nmaturity: seed\n---\n# Alpha\n\nSee [beta](beta.md).\n"
SOLO = "---\ntype: idea\nlayer: concept\nmaturity: seed\n---\n# Solo\n\nNo links.\n"
BETA = "---\ntype: idea\nlayer: concept\nmaturity: seed\n---\n# Beta\n\nBack to [alpha](alpha.md).\n"


@pytest.fixture
def bases(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("KB_BASES_DIR", str(tmp_path / "kbs"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k in ("KB", "KB_ROOT", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", inbox.ENV_URL, inbox.ENV_TOKEN):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "KEY_FILE", str(tmp_path / "nokey"))
    monkeypatch.setattr(llm, "_which", lambda n: None)
    return tmp_path / "kbs"


def make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


class FakeSite:
    """The Worker's inbox routes the Mac uses, in memory. `calls` records (method, path); `down` fails the status route."""
    def __init__(self):
        self.items, self.zips, self.calls, self.down = {}, {}, [], False

    def add(self, item, kind="zip", data=None, **fields):
        self.items[item] = {"item": item, "status": "pending", "kind": kind, "uploader": "me@example.com", "pages": 2, **fields}
        if data is not None:
            self.zips[item] = data

    def request(self, method, url, tok, body=None):
        assert tok == TOKEN and url.startswith("https://kb.example.test/")
        path = url[len("https://kb.example.test"):]
        self.calls.append((method, path))
        if path == "/api/inbox" or path.startswith("/api/inbox?status="):
            want = path.split("=")[1] if "=" in path else "all"
            rows = [i for i in self.items.values() if want in ("all", i["status"])]
            return 200, json.dumps({"items": rows}).encode()
        if path.endswith("/bundle"):
            return 200, self.zips[path.split("/")[3]]
        if path.endswith("/status"):
            if self.down:
                return 502, b"{}"
            self.items[path.split("/")[3]].update(body)
            return 200, b"{}"
        return 404, b"{}"


@pytest.fixture
def site():
    return FakeSite()


def client(site):
    return inbox.Client("https://kb.example.test", TOKEN, site.request)


def test_pull_imports_a_zip_as_a_new_kb_and_reports_it(bases, site):
    site.add("20261103T100000Z-aaaaaaaa", data=make_zip({"alpha.md": PAGE, "beta.md": BETA}), kb_id="from-site", kit="research")
    out = []
    result = inbox.pull(client(site), out=out.append)
    assert result.ok and result.imported == [("20261103T100000Z-aaaaaaaa", "from-site")]
    target = bases / "from-site"
    assert kbconfig.load_dir(str(target)).kit == "research"
    assert (target / "wiki" / "alpha.md").is_file()
    assert site.items["20261103T100000Z-aaaaaaaa"]["status"] == "imported"
    assert site.items["20261103T100000Z-aaaaaaaa"]["kb_id"] == "from-site"
    # nothing is published: the import made a kb folder and nothing else
    assert sorted(os.listdir(bases)) == ["from-site"]
    again = inbox.pull(client(site), out=out.append)               # the item is no longer pending: nothing to do
    assert again.imported == [] and "nothing pending" in out[-1]


def test_a_bad_item_is_reported_failed_and_the_next_still_imports(bases, site):
    site.add("20261103T100000Z-aaaaaaaa", data=make_zip({"../evil.md": PAGE}), kb_id="evil")          # zip-slip, defence in depth
    site.add("20261103T100100Z-bbbbbbbb", data=make_zip({"alpha.md": PAGE, "beta.md": BETA}), kb_id="good")
    result = inbox.pull(client(site), out=lambda *_: None)
    assert [i for i, _ in result.failed] == ["20261103T100000Z-aaaaaaaa"] and not result.ok
    assert site.items["20261103T100000Z-aaaaaaaa"]["status"] == "failed"
    assert "unsafe path" in site.items["20261103T100000Z-aaaaaaaa"]["error"]
    assert site.items["20261103T100100Z-bbbbbbbb"]["status"] == "imported"
    assert not (bases / "evil").exists() and (bases / "good").is_dir()


def test_a_taken_id_fails_the_item_with_the_importers_message(bases, site):
    site.add("20261103T100000Z-aaaaaaaa", data=make_zip({"alpha.md": SOLO}), kb_id="dup")
    site.add("20261103T100100Z-bbbbbbbb", data=make_zip({"alpha.md": SOLO}), kb_id="dup")
    inbox.pull(client(site), out=lambda *_: None)
    assert site.items["20261103T100000Z-aaaaaaaa"]["status"] == "imported"
    assert "already exists" in site.items["20261103T100100Z-bbbbbbbb"]["error"]


def test_a_git_item_is_cloned_here_not_on_the_site(bases, site):
    site.add("20261103T100000Z-aaaaaaaa", kind="git", git_url="https://github.com/octocat/notes.git#main", kb_id="octo")
    seen = []

    def fake_import(src, kit=None, kb_id=None, parent=None):
        seen.append((src, kit, kb_id))
        return str(bases / kb_id)

    result = inbox.pull(client(site), importer=fake_import, out=lambda *_: None)
    assert seen == [("https://github.com/octocat/notes.git#main", None, "octo")]
    assert result.imported == [("20261103T100000Z-aaaaaaaa", "octo")]
    assert not any(p.endswith("/bundle") for _m, p in site.calls)            # a git item has no zip to download


def test_dry_run_changes_nothing(bases, site):
    site.add("20261103T100000Z-aaaaaaaa", data=make_zip({"alpha.md": SOLO}), kb_id="x")
    out = []
    result = inbox.pull(client(site), dry_run=True, out=out.append)
    assert result.imported == [] and site.items["20261103T100000Z-aaaaaaaa"]["status"] == "pending"
    assert not bases.exists() and "would import" in out[0]
    assert [m for m, _p in site.calls] == ["GET"]


def test_an_import_the_site_never_heard_about_is_flagged(bases, site):
    site.add("20261103T100000Z-aaaaaaaa", data=make_zip({"alpha.md": SOLO}), kb_id="x")
    site.down = True
    result = inbox.pull(client(site), out=lambda *_: None)
    assert result.imported and result.unreported == ["20261103T100000Z-aaaaaaaa"] and not result.ok


def test_site_url_needs_https_and_the_token_never_shows(monkeypatch):
    with pytest.raises(inbox.InboxError, match="https"):
        monkeypatch.setenv(inbox.ENV_URL, "http://example.com")
        inbox.site_url()
    monkeypatch.setenv(inbox.ENV_URL, "http://localhost:8787/")
    assert inbox.site_url() == "http://localhost:8787"
    monkeypatch.setenv(inbox.ENV_URL, "https://kb.example.test/")
    assert inbox.site_url() == "https://kb.example.test"
    with pytest.raises(inbox.InboxError, match="no inbox token"):
        inbox.token(read=lambda: None)
    assert inbox.token(read=lambda: "from-keychain") == "from-keychain"
    monkeypatch.setenv(inbox.ENV_TOKEN, TOKEN)
    assert inbox.token(read=lambda: "from-keychain") == TOKEN                # the environment wins


@pytest.mark.parametrize("status, text", [(401, "refused the inbox token"), (403, "refused the inbox token"),
                                           (503, "not set up"), (0, "cannot reach"), (500, "answered 500")])
def test_site_errors_name_the_fix_and_never_the_token(status, text):
    c = inbox.Client("https://kb.example.test", TOKEN, lambda *a, **k: (status, b""))
    with pytest.raises(inbox.InboxError) as e:
        c.items()
    assert text in str(e.value) and TOKEN not in str(e.value)


def test_requests_carry_the_token_in_a_header_only(monkeypatch):
    seen = {}

    class Res:
        status = 200
        def read(self): return b"{}"
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Opener:
        def open(self, req, timeout=None):
            seen.update(url=req.full_url, auth=req.get_header("Authorization"), method=req.get_method())
            return Res()

    monkeypatch.setattr(inbox.urllib.request, "build_opener", lambda *handlers: Opener())
    assert inbox.http("GET", "https://kb.example.test/api/inbox?status=pending", TOKEN) == (200, b"{}")
    assert seen["auth"] == f"Bearer {TOKEN}" and TOKEN not in seen["url"]
    assert inbox._NoRedirect().redirect_request() is None                    # a redirect would carry the token elsewhere


def test_list_prints_rows_and_json(bases, site, monkeypatch, capsys):
    site.add("20261103T100000Z-aaaaaaaa", data=b"x", kb_id="x", pages=3)
    made = client(site)
    monkeypatch.setattr(inbox, "Client", lambda: made)
    assert inbox.main(["list"]) == 0
    assert "20261103T100000Z-aaaaaaaa" in capsys.readouterr().out
    assert inbox.main(["list", "--status", "all", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["kb_id"] == "x"


def test_a_missing_token_is_a_message_and_exit_1(bases, monkeypatch, capsys):
    monkeypatch.setenv(inbox.ENV_URL, "https://kb.example.test")
    monkeypatch.setattr(inbox, "keychain_token", lambda: None)
    assert inbox.main(["list"]) == 1
    assert "no inbox token" in capsys.readouterr().err


def test_the_command_is_registered_under_kb():
    path, cmd, rest = tree.resolve(["kb", "inbox", "pull", "--dry-run"])
    assert path == ("kb", "inbox") and cmd.target == "kb_distillery.inbox" and rest == ["pull", "--dry-run"]


# ---------- the daily-sync hook, behind the flag ----------

class Ran:
    def __init__(self, rc=0, boom=None):
        self.calls, self.rc, self.boom = [], rc, boom

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if self.boom:
            raise self.boom
        return type("P", (), {"returncode": self.rc})()


@pytest.mark.flag("inbox-pickup", False)
def test_flag_off_the_hook_does_nothing():
    from kb_distillery.ops import daily_sync
    ran = Ran()
    assert daily_sync.inbox_pickup(run=ran) is None and ran.calls == []


@pytest.mark.flag("inbox-pickup", True)
def test_flag_on_the_hook_runs_pull_and_never_raises(capsys):
    from kb_distillery.ops import daily_sync
    ran = Ran()
    assert daily_sync.inbox_pickup(run=ran) == 0
    assert ran.calls[0][1:] == ["-m", "kb_distillery.inbox", "pull"]
    assert daily_sync.inbox_pickup(run=Ran(rc=1)) == 1 and "exit 1" in capsys.readouterr().out
    assert daily_sync.inbox_pickup(run=Ran(boom=OSError("no python"))) is None and "skipped" in capsys.readouterr().out


def test_daily_sync_calls_the_hook_after_the_sync_but_not_on_a_dry_run(monkeypatch):
    from kb_distillery.ops import core, daily_sync
    order = []
    monkeypatch.setattr(core, "sync", lambda **k: order.append("sync") or 0)
    monkeypatch.setattr(daily_sync, "inbox_pickup", lambda *a, **k: order.append("inbox"))
    assert daily_sync.main(["--no-push"]) == 0
    assert order == ["sync", "inbox"]
    order.clear()
    assert daily_sync.main(["--dry-run"]) == 0
    assert order == ["sync"]
