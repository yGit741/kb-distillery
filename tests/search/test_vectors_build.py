"""The Python vector builder: writes the table the reader loads, skips unchanged cards, drops gone ones and other
models' rows, and says what to install when the optional model package is missing. A fake embedder: no model, no network."""
import hashlib
import sqlite3

import numpy as np
import pytest

from kb_distillery.search import vectors, vectors_build


class Fake:
    """Deterministic 8-d vectors from the text; counts what it was asked to embed."""

    def __init__(self):
        self.seen = []

    def passages(self, texts):
        self.seen += list(texts)
        return [np.frombuffer(hashlib.sha256(t.encode()).digest(), dtype=np.uint8)[:8].astype(np.float32) + 1 for t in texts]


def _kb(tmp_path, pages):
    (tmp_path / "wiki").mkdir()
    for slug, (title, desc) in pages.items():
        (tmp_path / "wiki" / f"{slug}.md").write_text(
            f'---\ntitle: "{title}"\ntype: concept\ndescription: "{desc}"\n---\n\n# {title}\n\nBody.\n', encoding="utf-8")
    return str(tmp_path)


def _build(root, fake, model="bge-small"):
    return vectors_build.build(root, model, make=lambda key: fake)


def test_builds_a_store_the_reader_loads(tmp_path):
    root = _kb(tmp_path, {"alpha": ("Alpha", "First page."), "beta": ("Beta", "Second page.")})
    r = _build(root, Fake())
    assert r == {"embedded": 2, "removed": 0, "unchanged": 0}
    v = vectors.load(str(tmp_path / ".cache" / "vectors.sqlite"))
    assert v.slugs == ["alpha", "beta"] and v.model == "BAAI/bge-small-en-v1.5"
    assert np.allclose(np.linalg.norm(v.m, axis=1), 1.0)
    ok, _ = vectors.status(str(tmp_path / ".cache" / "vectors.sqlite"), str(tmp_path / ".cache" / "qmd-cards"))
    assert ok


def test_only_changed_cards_are_embedded_and_gone_ones_removed(tmp_path):
    root = _kb(tmp_path, {"alpha": ("Alpha", "First."), "beta": ("Beta", "Second."), "gamma": ("Gamma", "Third.")})
    _build(root, Fake())
    (tmp_path / "wiki" / "beta.md").write_text('---\ntitle: "Beta"\ntype: concept\ndescription: "Changed."\n---\n\n# Beta\n', encoding="utf-8")
    (tmp_path / "wiki" / "gamma.md").unlink()
    fake = Fake()
    assert _build(root, fake) == {"embedded": 1, "removed": 1, "unchanged": 1}
    assert len(fake.seen) == 1 and "Changed." in fake.seen[0]
    assert vectors.load(str(tmp_path / ".cache" / "vectors.sqlite")).slugs == ["alpha", "beta"]


def test_up_to_date_store_loads_no_model(tmp_path):
    root = _kb(tmp_path, {"alpha": ("Alpha", "First.")})
    _build(root, Fake())

    def boom(key):
        raise AssertionError("model loaded for an up-to-date store")
    assert vectors_build.build(root, make=boom)["embedded"] == 0


def test_other_models_rows_are_rebuilt_not_mixed(tmp_path):
    root = _kb(tmp_path, {"alpha": ("Alpha", "First.")})
    _build(root, Fake())
    con = sqlite3.connect(tmp_path / ".cache" / "vectors.sqlite")
    con.execute("UPDATE vectors SET model = 'other'")
    con.commit()
    con.close()
    assert _build(root, Fake())["embedded"] == 1
    assert vectors.load(str(tmp_path / ".cache" / "vectors.sqlite")).model == "BAAI/bge-small-en-v1.5"


def test_no_cards_refuses(tmp_path):
    root = _kb(tmp_path, {})
    with pytest.raises(vectors_build.NothingToEmbed, match="no cards"):
        _build(root, Fake())


def test_status_reports_a_store_built_with_another_model(tmp_path):
    root = _kb(tmp_path, {"alpha": ("Alpha", "First.")})
    _build(root, Fake())
    assert vectors_build.status(root).startswith("ok")
    assert vectors_build.status(root, "qwen3-0.6b").startswith("behind") and "Qwen3" in vectors_build.status(root, "qwen3-0.6b")


def test_one_kb_without_pages_does_not_stop_the_others(tmp_path, monkeypatch, capsys):
    (tmp_path / "empty").mkdir()
    full = tmp_path / "full"
    full.mkdir()
    _kb(full, {"alpha": ("Alpha", "First.")})
    monkeypatch.setattr(vectors_build.kbconfig, "discover", lambda: {"a-empty": str(tmp_path / "empty"), "b-full": str(full)})
    monkeypatch.setattr(vectors_build, "Embedder", lambda key: Fake())
    assert vectors_build.main(["--all"]) == 1
    assert (full / ".cache" / "vectors.sqlite").exists() and "skipped" in capsys.readouterr().err


def test_missing_model_package_names_the_extra(tmp_path, monkeypatch):
    import builtins
    real = builtins.__import__

    def no_fastembed(name, *a, **k):
        if name.startswith("fastembed"):
            raise ImportError("no fastembed", name="fastembed")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_fastembed)
    with pytest.raises(vectors_build.EmbedderMissing, match=r"kb-distillery\[vectors\]"):
        vectors_build.Embedder("bge-small")


def test_main_all_builds_every_kb_and_reports_missing_package(tmp_path, monkeypatch, capsys):
    bases = tmp_path / "bases"
    for name in ("one", "two"):
        (bases / name).mkdir(parents=True)
        _kb(bases / name, {"alpha": ("Alpha", "First.")})
        (bases / name / "kb.toml").write_text("[kb]\n", encoding="utf-8")
    monkeypatch.setattr(vectors_build.kbconfig, "discover", lambda: {"one": str(bases / "one"), "two": str(bases / "two")})
    fake = Fake()
    monkeypatch.setattr(vectors_build, "Embedder", lambda key: fake)
    assert vectors_build.main(["--all"]) == 0
    assert len(fake.seen) == 2 and (bases / "two" / ".cache" / "vectors.sqlite").exists()
    assert vectors_build.main(["--all", "--status"]) == 0
    assert capsys.readouterr().out.count("ok ") == 2

    def missing(key):
        raise vectors_build.EmbedderMissing("install it")
    (bases / "one" / ".cache" / "vectors.sqlite").unlink()
    monkeypatch.setattr(vectors_build, "Embedder", missing)
    assert vectors_build.main(["--all"]) == 1
    assert "install it" in capsys.readouterr().err
