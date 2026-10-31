"""Backlog service: capture, plan intake (paths, plan status) and drift, against a throwaway repo."""
import os
import subprocess

import pytest

from kb.services import backlog as bl


def vcs(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "src" / "a.py").write_text("1\n")
    (r / "src" / "b.py").write_text("1\n")
    vcs(r, "init", "-q", "-b", "main")
    vcs(r, "add", ".")
    vcs(r, "commit", "-qm", "init")
    monkeypatch.setattr(bl, "primary_root", lambda: str(r))
    monkeypatch.setattr(bl, "CHECKOUT_ROOT", str(r))
    monkeypatch.setenv("KB_BACKLOG_DIR", str(tmp_path / "items"))
    return r


def commit(repo, path, text, msg):
    (repo / path).write_text(text)
    vcs(repo, "add", ".")
    vcs(repo, "commit", "-qm", msg)


def plan(tmp_path, text="Add the cache.\n\nTouch `src/a.py` and src/nope.py, also src/b.py.\n"):
    f = tmp_path / "plan.md"
    f.write_text(text)
    return str(f)


def test_idea_roundtrip(repo):
    i = bl.add_item("Try a dark graph theme", why="easier on the eyes", area="graph")
    assert i["status"] == "inbox" and i["plan_status"] == "no-plan" and i["paths"] == []
    got = bl.get_item(i["id"])
    assert got["why"] == "easier on the eyes" and got["drift"]["level"] == "none"
    assert [x["id"] for x in bl.list_items()["items"]] == [i["id"]]


def test_same_title_same_day_gets_a_unique_id(repo):
    a, b = bl.add_item("Same"), bl.add_item("Same")
    assert a["id"] != b["id"]


def test_rejects_bad_input(repo):
    with pytest.raises(bl.BacklogError):
        bl.add_item("  ")
    with pytest.raises(bl.BacklogError):
        bl.add_item("x", kind="epic")
    with pytest.raises(bl.BacklogError):
        bl.get_item("../../etc/passwd")


def test_plan_intake_records_base_and_only_tracked_paths(repo, tmp_path):
    i = bl.add_item("Add the cache", plan_file=plan(tmp_path))
    assert i["kind"] == "plan" and i["plan_status"] == "has-plan" and i["base_sha"]
    assert i["paths"] == ["src/a.py", "src/b.py"]          # src/nope.py is not a repo file
    assert "Touch" in bl.get_item(i["id"])["plan"]
    assert bl.list_items()["items"][0]["plan"] == ""       # the list carries no plan text


def test_drift_fresh_drifted_stale_and_maybe_done(repo, tmp_path):
    i = bl.add_item("Add the cache", plan_file=plan(tmp_path))
    assert bl.get_item(i["id"])["drift"]["level"] == "fresh"
    commit(repo, "src/a.py", "2\n", "tweak a")
    d = bl.get_item(i["id"])["drift"]
    assert d["level"] == "drifted" and d["commits"] == 1
    vcs(repo, "rm", "-q", "src/b.py")
    vcs(repo, "commit", "-qm", "drop b")
    d = bl.get_item(i["id"])["drift"]
    assert d["level"] == "stale" and d["missing"] == ["src/b.py"]
    commit(repo, "src/a.py", "3\n", "feat(cache): add the cache (#9)")
    assert bl.get_item(i["id"])["drift"]["level"] == "maybe-done"


def test_unrelated_commits_do_not_drift(repo, tmp_path):
    i = bl.add_item("Add the cache", plan_file=plan(tmp_path))
    commit(repo, "other.txt", "x\n", "unrelated")
    assert bl.get_item(i["id"])["drift"]["level"] == "fresh"


def test_status_move_keeps_plan_and_closed_items_do_not_drift(repo, tmp_path):
    i = bl.add_item("Add the cache", plan_file=plan(tmp_path))
    assert bl.set_status(i["id"], "next")["status"] == "next"
    assert bl.get_item(i["id"])["plan"]
    assert bl.set_status(i["id"], "done")["drift"]["level"] == "closed"
    with pytest.raises(bl.BacklogError):
        bl.set_status(i["id"], "someday")


def test_list_orders_by_status_and_skips_broken_files(repo):
    a, b = bl.add_item("A"), bl.add_item("B")
    bl.set_status(a["id"], "doing")
    with open(os.path.join(bl.backlog_dir(), "junk.md"), "w") as f:
        f.write("no frontmatter")
    assert [x["id"] for x in bl.list_items()["items"]] == [b["id"], a["id"]]   # inbox before doing
