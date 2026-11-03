"""`ops view pin|unpin|rename`: meta/views.json changes as one kb(refine) step each, on a temp kb repo (never a real one);
`.local/` is never staged by the ops commit path."""
import json
import os
import re
import subprocess
from unittest import mock

import pytest

from kb_distillery import init_kb
from kb_distillery.ops import core
from kb_distillery.ops import view as ops_view
from kb_distillery.ops.__main__ import main as ops_main
from kb_distillery.vault import views as vv
from kb_distillery.vault.views import ViewsError

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "KB_NO_PUSH": "1"}
SUBJECT = re.compile(r"^kb\(refine\): (?P<summary>.+) \(kb-\d+\.\d+\.\d+\)$")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout.strip()


def make_repo(root, gitignore="meta/.ops/\n"):
    """A tiny kb repo on main with one commit (the kb's own layout, no kb.toml: lint is mocked)."""
    for rel, text in {"wiki/log.md": "# Log\n", "wiki/index.md": "v1\n", ".gitignore": gitignore}.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@t")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: init (retro)")
    return root


@pytest.fixture
def kb(tmp_path):
    root = make_repo(str(tmp_path))
    with mock.patch.dict(os.environ, ENV), \
         mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"), \
         mock.patch("kb_distillery.ops.core.run_lint", return_value=None):     # lint of a bare temp repo is not under test
        yield root


def commits(root):
    return int(git(root, "rev-list", "--count", "HEAD"))


def head_files(root):
    return set(filter(None, git(root, "show", "--name-only", "--format=", "HEAD").split("\n")))


def stored(root):
    with open(os.path.join(root, "meta", "views.json"), encoding="utf-8") as f:
        return json.load(f)


def test_pin_rename_unpin_one_step_each(kb):
    n = commits(kb)
    spec = {"cypher": "MATCH (n) RETURN n", "camera": {"x": 1}}

    out = ops_view.pin("Open questions", spec, root=kb)
    assert out["ok"] and out["view"]["id"] == "open-questions" and out["version"].startswith("kb-")
    assert commits(kb) == n + 1
    msg = git(kb, "log", "-1", "--format=%B")
    m = SUBJECT.match(msg.splitlines()[0])
    assert m and m["summary"] == "pin view Open questions"
    assert "KB-Op: refine" in msg and "KB-Target: open-questions" in msg
    assert head_files(kb) == {"meta/views.json", "wiki/log.md"}
    [v] = stored(kb)
    assert v["id"] == "open-questions" and v["name"] == "Open questions" and v["spec"] == spec
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", v["created"])
    assert "refine | pin view Open questions" in open(os.path.join(kb, "wiki", "log.md")).read()

    out = ops_view.rename("open-questions", "Questions", root=kb)
    assert commits(kb) == n + 2 and out["view"]["name"] == "Questions"
    assert SUBJECT.match(git(kb, "log", "-1", "--format=%s"))["summary"] == "rename view Open questions to Questions"
    [v2] = stored(kb)
    assert (v2["id"], v2["created"], v2["spec"]) == (v["id"], v["created"], spec)       # only the name moved

    out = ops_view.unpin("open-questions", root=kb)
    assert commits(kb) == n + 3 and out["view"]["id"] == "open-questions"
    assert SUBJECT.match(git(kb, "log", "-1", "--format=%s"))["summary"] == "unpin view Questions"
    assert not os.path.exists(os.path.join(kb, "meta", "views.json"))
    assert git(kb, "status", "--porcelain") == ""


def test_ids_stay_unique_and_explicit_ids_conflict(kb):
    a = ops_view.pin("Same name", {}, root=kb)["view"]["id"]
    b = ops_view.pin("Same name", {}, root=kb)["view"]["id"]
    assert (a, b) == ("same-name", "same-name-2")
    assert ops_view.pin("x", {}, view_id="mine", root=kb)["view"]["id"] == "mine"
    n = commits(kb)
    with pytest.raises(ViewsError) as e:
        ops_view.pin("y", {}, view_id="mine", root=kb)
    assert e.value.status == 409 and commits(kb) == n


@pytest.mark.parametrize("call, status", [
    (lambda kb: ops_view.pin("", {}, root=kb), 400),
    (lambda kb: ops_view.pin("x" * 200, {}, root=kb), 400),
    (lambda kb: ops_view.pin("ok", {}, view_id="Bad Id", root=kb), 400),
    (lambda kb: ops_view.pin("ok", ["not", "an", "object"], root=kb), 400),
    (lambda kb: ops_view.unpin("missing", root=kb), 404),
    (lambda kb: ops_view.rename("missing", "x", root=kb), 404),
])
def test_refusals_change_nothing(kb, call, status):
    n = commits(kb)
    with pytest.raises(ViewsError) as e:
        call(kb)
    assert e.value.status == status and commits(kb) == n
    assert not os.path.exists(os.path.join(kb, "meta", "views.json"))


def test_renaming_to_the_same_name_makes_no_step(kb):
    ops_view.pin("Keep", {}, root=kb)
    n = commits(kb)
    out = ops_view.rename("keep", "  Keep ", root=kb)
    assert out["sha"] is None and commits(kb) == n


def test_open_session_blocks_and_failed_step_restores_the_file(kb):
    ops_view.pin("First", {"a": 1}, root=kb)
    before = open(os.path.join(kb, "meta", "views.json")).read()
    with mock.patch.object(core, "commit_op", side_effect=core.OpsError("lint said no")):
        with pytest.raises(ViewsError) as e:
            ops_view.pin("Second", {}, root=kb)
    assert e.value.status == 500 and "lint said no" in str(e.value)
    assert open(os.path.join(kb, "meta", "views.json")).read() == before

    core.begin("refine", "something", root=kb)
    n = commits(kb)
    with pytest.raises(ViewsError) as e:
        ops_view.pin("Third", {}, root=kb)
    assert e.value.status == 409 and "ops session" in str(e.value) and commits(kb) == n


def test_a_damaged_file_is_a_409_not_a_guess(kb):
    os.makedirs(os.path.join(kb, "meta"))
    with open(os.path.join(kb, "meta", "views.json"), "w") as f:
        f.write("{not json")
    with pytest.raises(ViewsError) as e:
        ops_view.pin("x", {}, root=kb)
    assert e.value.status == 409


def test_undo_reverts_a_view_step(kb):
    ops_view.pin("Undoable", {}, root=kb)
    sha = git(kb, "rev-parse", "HEAD")
    core.undo(sha, root=kb)
    assert not os.path.exists(os.path.join(kb, "meta", "views.json"))
    assert git(kb, "log", "-1", "--format=%s").startswith("kb(undo): ")


def test_cli_pin_rename_unpin(kb, capsys):
    with mock.patch.object(core, "ROOT", kb):
        assert ops_main(["view", "pin", "From CLI", "--spec", '{"k": [1, 2]}']) == 0
        assert "pinned view from-cli (kb-" in capsys.readouterr().out
        assert stored(kb)[0]["spec"] == {"k": [1, 2]}
        assert ops_main(["view", "rename", "from-cli", "Renamed"]) == 0
        assert ops_main(["view", "unpin", "from-cli"]) == 0
        assert ops_main(["view", "unpin", "from-cli"]) == 1          # unknown now: a message, exit 1
        assert "no pinned view" in capsys.readouterr().err
        assert ops_main(["view", "pin", "Bad", "--spec", "{oops"]) == 1


# ---------- .local/ is never committed ----------

def test_the_ops_commit_path_never_stages_local_state(kb):
    """A kb whose .gitignore predates the `.local/` rule: the file sits untracked and no ops path takes it."""
    assert ".local" not in open(os.path.join(kb, ".gitignore")).read()
    local = os.path.join(kb, ".local", "recent.json")
    os.makedirs(os.path.dirname(local))
    with open(local, "w") as f:
        f.write("[]\n")

    ops_view.pin("With local state around", {}, root=kb)           # the normal path
    assert head_files(kb) == {"meta/views.json", "wiki/log.md"}

    with open(os.path.join(kb, "wiki", "a.md"), "w") as f:         # a path list that names it explicitly
        f.write("x\n")
    core.commit_op("refine", "a", "edit a", paths=["wiki/a.md", ".local/recent.json"], root=kb)
    assert ".local/recent.json" not in head_files(kb)

    assert core._commit_paths(kb, [".local/recent.json", ".local"], "kb(refine): x (kb-1.5.99)\n") is None
    assert git(kb, "ls-files", ".local") == ""
    assert git(kb, "diff", "--cached", "--name-only") == ""


def test_init_writes_the_local_rule_into_a_new_kbs_gitignore():
    assert ".local/" in init_kb.GITIGNORE.splitlines()
