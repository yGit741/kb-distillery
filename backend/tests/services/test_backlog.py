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


def test_plan_with_its_own_headings_survives_a_status_move(repo, tmp_path):
    text = "## Why\nbecause\n\n## Plan\n1. do it\n\n## Why again\n<!-- not a marker -->\n## Steps\nx\n"
    i = bl.add_item("Headings", why="short why", plan_file=plan(tmp_path, text))
    assert bl.get_item(i["id"])["plan"] == text.strip()
    assert bl.get_item(i["id"])["why"] == "short why"
    bl.set_status(i["id"], "next")
    again = bl.get_item(i["id"])
    assert again["plan"] == text.strip() and again["why"] == "short why"


def test_title_with_colon_and_dashes_roundtrips(repo):
    i = bl.add_item("Fix: the --- thing: now")
    assert bl.get_item(i["id"])["title"] == "Fix: the --- thing: now"


def test_hand_edited_card_is_read_leniently(repo):
    good = bl.add_item("Good")
    path = os.path.join(bl.backlog_dir(), "hand.md")
    with open(path, "w") as f:   # area stripped of its trailing space, size missing, odd status, bad paths JSON
        f.write("---\ntitle: By hand\nkind: epic\narea:\nstatus: todo\npaths: [oops\n---\n")
    items = {x["id"]: x for x in bl.list_items()["items"]}
    assert set(items) == {good["id"], "hand"}
    hand = items["hand"]
    assert (hand["area"], hand["size"], hand["kind"], hand["status"], hand["paths"]) == ("", "m", "idea", "inbox", [])
    assert bl.get_item("hand")["title"] == "By hand"       # show / status do not crash either


def test_id_is_a_basename_not_a_path(repo, tmp_path):
    (tmp_path / "secret.md").write_text("---\ntitle: leaked\n---\n")
    bl.add_item("x")
    with pytest.raises(bl.BacklogError):
        bl.get_item("../secret")


def test_dot_directories_and_dotfiles_are_tracked(repo, tmp_path):
    (repo / ".cursor").mkdir()
    (repo / ".cursor" / "rule.mdc").write_text("1\n")
    (repo / ".gitignore").write_text("x\n")
    vcs(repo, "add", ".")
    vcs(repo, "commit", "-qm", "dot files")
    i = bl.add_item("Dots", plan_file=plan(tmp_path, "See .cursor/rule.mdc, ./src/a.py, and .gitignore."))
    assert i["paths"] == [".cursor/rule.mdc", "src/a.py", ".gitignore"]


def test_list_filters_by_status(repo):
    a, _ = bl.add_item("A"), bl.add_item("B")
    bl.set_status(a["id"], "next")
    assert [x["id"] for x in bl.list_items(status="next")["items"]] == [a["id"]]


def test_list_orders_by_status_and_skips_broken_files(repo):
    a, b = bl.add_item("A"), bl.add_item("B")
    bl.set_status(a["id"], "doing")
    with open(os.path.join(bl.backlog_dir(), "junk.md"), "w") as f:
        f.write("no frontmatter")
    assert [x["id"] for x in bl.list_items()["items"]] == [b["id"], a["id"]]   # inbox before doing
