"""`ops favorite add|remove|list` as knowledge steps, and the page-removal guard, on a temp kb repo (never a real one)."""
import os
import re
from unittest import mock

import pytest

from kb_distillery.ops import core
from kb_distillery.ops import favorite as ops_fav
from kb_distillery.ops.__main__ import main as ops_main
from kb_distillery.vault import favorites as fv
from kb_distillery.vault.favorites import FavoritesError
from tests.ops.test_view import ENV, commits, git, head_files, make_repo

SUBJECT = re.compile(r"^kb\(refine\): (?P<summary>.+) \(kb-\d+\.\d+\.\d+\)$")
PAGE = "---\ntype: idea\nlayer: concept\ndescription: About {n}.\n---\n\n# {n}\n\n{body}\n"


def write_page(root, slug, body="Some text about the idea.\nA second line.\nA third line.\n"):
    path = os.path.join(root, "wiki", slug + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(PAGE.format(n=slug, body=body))
    return path


@pytest.fixture
def kb(tmp_path):
    root = make_repo(str(tmp_path))
    for slug in ("alpha", "beta", "gamma"):
        write_page(root, slug)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: pages (retro)")
    with mock.patch.dict(os.environ, ENV), \
         mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped"), \
         mock.patch("kb_distillery.ops.core.run_lint", return_value=None), \
         mock.patch("kb_distillery.ops.core.okf_gate", return_value=None):
        yield root


def test_add_remove_list_are_one_step_each(kb):
    n = commits(kb)
    out = ops_fav.add("beta", root=kb)
    assert out["ok"] and out["slugs"] == ["beta"] and out["version"].startswith("kb-")
    assert commits(kb) == n + 1
    assert SUBJECT.match(git(kb, "log", "-1", "--format=%s"))["summary"] == "favorite add beta"
    assert head_files(kb) == {"meta/favorites.json", "wiki/log.md"}

    ops_fav.add("alpha", root=kb)
    assert ops_fav.list_slugs(root=kb) == ["alpha", "beta"] and commits(kb) == n + 2

    out = ops_fav.remove("beta", root=kb)
    assert out["ok"] and out["slugs"] == ["alpha"] and commits(kb) == n + 3
    assert SUBJECT.match(git(kb, "log", "-1", "--format=%s"))["summary"] == "favorite remove beta"


def test_noops_make_no_step(kb):
    ops_fav.add("alpha", root=kb)
    n = commits(kb)
    again = ops_fav.add("alpha", root=kb)
    assert again["ok"] is False and again["reason"] == "already" and again["sha"] is None
    gone = ops_fav.remove("beta", root=kb)
    assert gone["ok"] is False and gone["reason"] == "absent"
    assert commits(kb) == n


def test_add_of_a_non_page_is_an_error(kb):
    n = commits(kb)
    for slug in ("nope", "index", "log"):
        with pytest.raises(FavoritesError) as e:
            ops_fav.add(slug, root=kb)
        assert e.value.status == 404
    assert commits(kb) == n and not os.path.exists(os.path.join(kb, fv.FAVORITES_REL))


def test_cli_add_list_remove(kb, capsys):
    with mock.patch.object(core, "ROOT", kb):
        assert ops_main(["favorite", "add", "gamma", "--no-push"]) == 0
        assert ops_main(["favorite", "list"]) == 0
        assert capsys.readouterr().out.strip().splitlines()[-1] == "gamma"
        assert ops_main(["favorite", "add", "nope", "--no-push"]) == 1
        assert ops_main(["favorite", "remove", "gamma", "--no-push"]) == 0
        assert fv.load(kb) == []


def edit_session(root, edit, **commit_kw):
    core.begin("refine", "restructure", "x", root=root)
    edit()
    return core.commit(root=root, **commit_kw)


@pytest.mark.parametrize("how", ["delete", "merge", "split"])
def test_removing_a_favorite_page_is_refused_then_allowed_with_confirm(kb, how):
    ops_fav.add("beta", root=kb)
    ops_fav.add("alpha", root=kb)
    page = os.path.join(kb, "wiki", "beta.md")

    def edit():
        if how == "merge":                               # beta folded into alpha, then dropped
            with open(os.path.join(kb, "wiki", "alpha.md"), "a", encoding="utf-8") as f:
                f.write("\nMerged from beta.\n")
        if how == "split":                               # the original is replaced by two new, different pages
            write_page(kb, "beta-one", body="Entirely different words one.\nUnrelated two.\n")
            write_page(kb, "beta-two", body="Other sentences here.\nAnd more here.\n")
        os.remove(page)

    n = commits(kb)
    core.begin("refine", how, "x", root=kb)
    edit()
    with pytest.raises(core.OpsError, match="beta is a favorite: pass --confirm-favorite to delete it"):
        core.commit(root=kb)
    assert commits(kb) == n and fv.load(kb) == ["alpha", "beta"]
    core.commit(root=kb, confirm_favorite=True)          # the session is still open: the same commit, now confirmed
    assert commits(kb) == n + 1 and fv.load(kb) == ["alpha"]
    assert "meta/favorites.json" in head_files(kb) and "wiki/beta.md" in head_files(kb)


def test_removing_a_page_that_is_not_a_favorite_needs_no_confirm(kb):
    ops_fav.add("alpha", root=kb)
    n = commits(kb)
    edit_session(kb, lambda: os.remove(os.path.join(kb, "wiki", "gamma.md")))
    assert commits(kb) == n + 1 and fv.load(kb) == ["alpha"]


def test_rename_follows(kb):
    ops_fav.add("beta", root=kb)
    n = commits(kb)

    def edit():
        os.rename(os.path.join(kb, "wiki", "beta.md"), os.path.join(kb, "wiki", "beta-renamed.md"))

    edit_session(kb, edit)                               # no confirm needed: the page lives on under a new slug
    assert commits(kb) == n + 1 and fv.load(kb) == ["beta-renamed"]
    assert "meta/favorites.json" in head_files(kb)


def test_record_path_is_guarded_too(kb, capsys):
    ops_fav.add("beta", root=kb)
    os.remove(os.path.join(kb, "wiki", "beta.md"))
    with mock.patch.object(core, "ROOT", kb):
        assert ops_main(["record", "refine", "beta", "drop beta", "wiki/beta.md", "--no-push"]) == 1
        assert "beta is a favorite" in capsys.readouterr().err
        assert fv.load(kb) == ["beta"]
        assert ops_main(["record", "refine", "beta", "drop beta", "wiki/beta.md", "--no-push", "--confirm-favorite"]) == 0
    assert fv.load(kb) == []


def test_guard_function(kb):
    ops_fav.add("beta", root=kb)
    assert ops_fav.guard(kb, ["alpha"], False) == []
    with pytest.raises(core.OpsError):
        ops_fav.guard(kb, ["beta", "alpha"], False)
    assert ops_fav.guard(kb, ["beta"], True) == ["beta"]
