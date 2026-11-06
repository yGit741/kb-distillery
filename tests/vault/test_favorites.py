"""meta/favorites.json: read, write, sort, validate (pure file logic, temp dirs only)."""
import json
import os

import pytest

from kb_distillery.vault import favorites as fv
from kb_distillery.vault import schema
from kb_distillery.vault.favorites import FavoritesError


def test_missing_and_blank_are_empty(tmp_path):
    assert fv.load(str(tmp_path)) == [] and fv.parse("") == [] and fv.parse(None) == []


def test_write_sorts_dedupes_and_round_trips(tmp_path):
    root = str(tmp_path)
    fv.write(root, ["zeta", "alpha", "alpha", "learning-theory"])
    with open(os.path.join(root, fv.FAVORITES_REL), encoding="utf-8") as f:
        text = f.read()
    assert json.loads(text) == {"v": 1, "slugs": ["alpha", "learning-theory", "zeta"]} and text.endswith("\n")
    assert fv.load(root) == ["alpha", "learning-theory", "zeta"]
    fv.write(root, [])                                   # an empty list removes the file
    assert not os.path.exists(os.path.join(root, fv.FAVORITES_REL))


@pytest.mark.parametrize("bad", ["", "a/b", "../x", "-x", "has space", None, 3])
def test_clean_slug_rejects(bad):
    with pytest.raises(FavoritesError) as e:
        fv.clean_slug(bad)
    assert e.value.status == 400


@pytest.mark.parametrize("text", ["{", "[]", '{"slugs": "x"}', '{"slugs": ["a/b"]}'])
def test_damaged_file_is_a_409(text):
    with pytest.raises(FavoritesError) as e:
        fv.parse(text)
    assert e.value.status == 409


def test_page_slugs_skip_reserved_files(tmp_path):
    wiki = tmp_path / "wiki" / "sub"
    wiki.mkdir(parents=True)
    for rel in ("alpha.md", "index.md", "log.md"):
        (tmp_path / "wiki" / rel).write_text("x\n")
    (wiki / "beta.md").write_text("x\n")
    assert fv.page_slugs(str(tmp_path)) == {"alpha", "beta"}


def test_favorites_file_is_a_known_knowledge_file():
    assert schema.lane_of(fv.FAVORITES_REL) == "knowledge"
    assert fv.FAVORITES_REL in schema.KNOWLEDGE_PATHS and fv.FAVORITES_REL in schema.RESTORABLE_PATHS
