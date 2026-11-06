"""The full-text index (kb_distillery.search.fts) on a temp kb: a page, a think note, a chat and a raw text file."""
import json
import os
import time
from unittest import mock

import pytest

from kb_distillery.search import fts


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


@pytest.fixture
def kb(tmp_path):
    root = str(tmp_path / "kb")
    think = str(tmp_path / "think")
    _w(f"{root}/wiki/tensor-rank.md", "---\ntype: idea\n---\n\n# Tensor rank\n\nThe minimal number of rank-one terms. Café résumé.\n")
    _w(f"{root}/wiki/index.md", "# index\n\ntensor everywhere\n")
    _w(f"{root}/raw/papers/grokking.md", "---\ntitle: Grokking paper\n---\n\nDelayed generalization after overfitting.\n")
    _w(f"{root}/raw/images/x.md", "tensor image sidecar\n")
    _w(f"{think}/ideas/compression.md", "# Compression idea\n\nTry a tensor decomposition of the cache.\n")
    _w(f"{root}/.local/sessions/s1.json", json.dumps({"id": "s1", "title": "Rank chat", "messages": [
        {"role": "user", "content": "what is a hessian eigenvalue?"}, {"role": "assistant", "content": "It measures curvature."}]}))
    _w(f"{root}/.local/sessions/s1.pins.json", json.dumps({"messages": [{"content": "ignored sidecar"}]}))
    with mock.patch.object(fts.kbconfig, "think_root", return_value=think):
        yield root


def ids(hits):
    return {(h["kind"], h["id"]) for h in hits}


def test_build_and_search_every_kind(kb):
    assert fts.build(kb) == 4
    assert os.path.isfile(os.path.join(kb, ".cache", "search", "fts.sqlite"))
    assert ids(fts.search(kb, "tensor")) == {("page", "tensor-rank"), ("think", "ideas/compression")}
    assert ids(fts.search(kb, "hessian")) == {("chat", "s1")}
    assert ids(fts.search(kb, "overfitting")) == {("raw", "raw/papers/grokking.md")}
    assert ids(fts.search(kb, "tensor", kinds=["think"])) == {("think", "ideas/compression")}
    assert fts.search(kb, "ignored") == []          # a sidecar is not a chat
    assert fts.search(kb, "image") == []            # raw/images is skipped
    hit = fts.search(kb, "rank-one")[0]
    assert hit["title"] == "Tensor rank" and "rank" in hit["snippet"] and hit["score"] > 0


def test_diacritics_prefix_and_title_weight(kb):
    assert ids(fts.search(kb, "cafe resume")) == {("page", "tensor-rank")}
    assert ids(fts.search(kb, "hess")) == {("chat", "s1")}            # prefix match on the last word
    assert fts.search(kb, "hessian eigen") and not fts.search(kb, "hessian zzz")
    first = fts.search(kb, "tensor rank")[0]
    assert first["id"] == "tensor-rank"


@pytest.mark.parametrize("raw", ['"', "tensor AND", "tensor OR NOT", "title:tensor", "tensor*(", "NEAR(tensor rank)", "'; DROP TABLE docs;--", "   ", "-", "^tensor"])
def test_query_is_sanitised(kb, raw):
    assert isinstance(fts.search(kb, raw), list)                      # never raises


def test_operators_are_plain_words(kb):
    assert fts.search(kb, "title:tensor") == fts.search(kb, "title tensor") == []      # "title" is not in any text
    assert ids(fts.search(kb, "tensor OR zzzz")) == set()                             # OR is a word, not an operator
    assert ids(fts.search(kb, '"tensor" rank')) == {("page", "tensor-rank")}


def test_fts_query_shape():
    assert fts.fts_query('say "hello" AND wor') == '"say" "hello" "AND" "wor"*'
    assert fts.fts_query("***") is None and fts.fts_query("") is None and fts.fts_query(None) is None
    assert fts.fts_query("x") == '"x"*'


def test_stale_detection_and_incremental_refresh(kb):
    assert fts.is_stale(kb)                                           # no index yet
    fts.search(kb, "tensor")                                          # first search builds it
    assert not fts.is_stale(kb)
    time.sleep(0.01)
    _w(f"{kb}/wiki/new-page.md", "# New page\n\nQuokka habitat.\n")
    assert fts.is_stale(kb)
    assert ids(fts.search(kb, "quokka")) == {("page", "new-page")}    # search refreshed it by itself
    assert not fts.is_stale(kb)
    os.remove(f"{kb}/wiki/new-page.md")
    assert fts.is_stale(kb)
    assert fts.search(kb, "quokka") == []


def test_update_only_touches_given_paths(kb):
    fts.build(kb)
    _w(f"{kb}/wiki/tensor-rank.md", "# Tensor rank\n\nNow about zebras.\n")
    _w(f"{kb}/wiki/other.md", "# Other\n\nlemur\n")
    assert fts.update(kb, ["wiki/tensor-rank.md"]) == 1
    db = fts._connect(kb)
    try:
        assert {r[0] for r in db.execute("SELECT ref FROM docs WHERE kind='page'")} == {"tensor-rank"}   # other.md not indexed yet
    finally:
        db.close()
    assert fts.is_stale(kb)                                           # the partial update did not hide it
    assert ids(fts.search(kb, "zebras")) == {("page", "tensor-rank")}
    assert ids(fts.search(kb, "lemur")) == {("page", "other")}
    os.remove(f"{kb}/wiki/other.md")
    assert fts.update(kb, [f"{kb}/wiki/other.md"]) == 1 and fts.search(kb, "lemur") == []


def test_update_without_index_does_nothing_and_never_raises(kb):
    assert fts.update(kb, ["wiki/tensor-rank.md"]) == 0
    assert not os.path.exists(fts.index_path(kb))
    fts.update_quiet(kb, ["wiki/tensor-rank.md"])
    fts.update_quiet(kb)
    assert not os.path.exists(fts.index_path(kb))
    with mock.patch.object(fts, "update", side_effect=RuntimeError("boom")):
        fts.update_quiet(kb, ["x"])


def test_rebuild_and_empty_kb(tmp_path):
    root = str(tmp_path / "empty")
    with mock.patch.object(fts.kbconfig, "think_root", return_value=str(tmp_path / "nothink")):
        assert fts.search(root, "anything") == []
        assert fts.build(root, rebuild=True) == 0


def test_writer_hooks_keep_the_index_fresh(kb):
    from kb_distillery.services import sessions_store as ss
    from kb_distillery.services import think as think_svc
    fts.build(kb)
    with mock.patch.object(ss, "_check_writable"):
        ss.put_session("s2", [{"role": "user", "content": "narwhal tusks"}], root=kb)
    assert ids(fts.search(kb, "narwhal")) == {("chat", "s2")}
    assert not fts.is_stale(kb)
    with mock.patch.object(think_svc, "_think_dir", return_value=os.path.join(os.path.dirname(kb), "think")):
        think_svc.save_note("newnote.md", "# Fresh\n\nplatypus\n", root=kb, create=True)
    assert ids(fts.search(kb, "platypus")) == {("think", "newnote")}


def test_cli_prints_hits(kb, capsys):
    with mock.patch("kb_distillery.config.paths.vault_root", return_value=kb):
        assert fts.main(["hessian", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == "s1"
    with mock.patch("kb_distillery.config.paths.vault_root", return_value=kb):
        assert fts.main(["--rebuild"]) == 0
        assert fts.main([]) == 2
