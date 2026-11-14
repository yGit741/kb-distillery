import json
import os

import pytest

from kb_distillery.parse import FLAG, enabled, store
from kb_distillery.parse.reconcile import Flag

SHA = store.sha1_bytes(b"%PDF-1.4 fixture")


def test_roundtrip_and_status(tmp_path):
    root = str(tmp_path / "parsed")
    flag = Flag("lost", 2, "'x' is missing", "x")
    store.write_page(root, SHA, 1, "# one", [], engine="t")
    store.write_page(root, SHA, 2, "two", [flag])
    store.write_page(root, SHA, 3, "three fixed", [], status="repaired", repaired_from="two")
    assert store.read_page(root, SHA, 1)["status"] == "verified"
    assert store.read_page(root, SHA, 2)["status"] == "needs-human"
    assert store.read_page(root, SHA, 2)["flags"][0]["kind"] == "lost"
    assert store.read_page(root, SHA, 3)["repaired_from"] == "two"
    assert store.read_page(root, SHA, 9) is None
    assert sorted(os.listdir(os.path.join(root, SHA))) == ["p0001.json", "p0002.json", "p0003.json"]
    m = store.write_manifest(root, SHA, "raw/book.pdf", 4, engine="t")
    assert m["status"] == {"verified": 1, "repaired": 1, "marked": 0, "needs-human": 1} and m["missing"] == [4]
    assert store.read_manifest(root, SHA) == m
    assert json.load(open(os.path.join(root, SHA, "manifest.json")))["sha1"] == SHA


def test_a_verified_page_cannot_carry_flags_and_statuses_are_closed(tmp_path):
    root = str(tmp_path)
    with pytest.raises(ValueError):
        store.write_page(root, SHA, 1, "x", [Flag("lost", 1, "d")], status="verified")
    with pytest.raises(ValueError):
        store.write_page(root, SHA, 1, "x", [], status="maybe")
    with pytest.raises(ValueError):
        store.write_page(root, SHA, 1, "x", [Flag("lost", 1, "d")], status="repaired", repaired_from="y")
    with pytest.raises(ValueError):
        store.write_page(root, SHA, 1, "x", [], status="repaired")
    with pytest.raises(ValueError):
        store.write_page(root, "../evil", 1, "x", [])


def test_checked_text_needs_every_page_checked(tmp_path):
    root = str(tmp_path)
    store.write_page(root, SHA, 1, "alpha", [])
    store.write_page(root, SHA, 2, "beta", [], status="repaired", repaired_from="b")
    assert store.checked_text(root, SHA) is None                       # no manifest: not known to be the whole document
    store.write_manifest(root, SHA, "x.pdf", 3)
    assert store.checked_text(root, SHA) is None                       # page 3 not stored yet
    assert store.checked_text(root, SHA, [1, 2]) == "alpha\n\nbeta"
    store.write_manifest(root, SHA, "x.pdf", 2)
    assert store.checked_text(root, SHA) == "alpha\n\nbeta"
    assert store.checked_text(root, SHA, [2]) == "beta"
    store.write_page(root, SHA, 3, "gamma", [Flag("lost", 3, "d")])
    store.write_manifest(root, SHA, "x.pdf", 3)
    assert store.checked_text(root, SHA) is None and store.checked_text(root, SHA, [1, 2]) == "alpha\n\nbeta"
    assert store.checked_text(root, SHA, [7]) is None
    assert store.checked_text(root, "ab" * 20) is None


def test_no_temp_files_left_behind(tmp_path):
    store.write_page(str(tmp_path), SHA, 1, "x", [])
    assert not [n for n in os.listdir(os.path.join(str(tmp_path), SHA)) if n.endswith(".tmp")]


@pytest.mark.flag("parsed-pdf", True)
def test_flag_on():
    assert FLAG == "parsed-pdf" and enabled() is True


@pytest.mark.flag("parsed-pdf", False)
def test_flag_off():
    assert enabled() is False


def test_flag_is_registered_and_dark_by_default():
    from kb_distillery.config.flags import registry
    f = registry.load().get(FLAG)
    assert f.default is False and not any([f.envs.local, f.envs.private, f.envs.public])
