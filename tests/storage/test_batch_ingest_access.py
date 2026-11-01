"""Modules migrated onto kb_distillery.storage keep their behaviour on a real folder and cannot be pointed outside raw/."""
import os
import zipfile

import pytest

from kb_distillery.ingest import chat_build, digest_many
from kb_distillery.publish import export
from kb_distillery.storage import StorageError, for_kb

CLIP = """---
clipped: 2026-01-02
source: https://example.org/c/1
---

**You**
hello

**Gemini**
hi there
"""


@pytest.fixture
def kb_root(tmp_path):
    (tmp_path / "raw" / "llm-chats").mkdir(parents=True)
    (tmp_path / "raw" / "llm-chats" / "a.md").write_text(CLIP, encoding="utf-8")
    (tmp_path / "raw" / "llm-chats" / "b.txt").write_text("not a clip")
    (tmp_path / "raw" / "llm-chats" / ".hidden.md").write_text("x")
    (tmp_path / "outside.md").write_text("secret")
    return tmp_path


def test_chat_build_lists_and_reads_clips_through_the_connector(kb_root):
    assert chat_build.clip_paths(str(kb_root)) == ["raw/llm-chats/a.md"]
    fm, turns, sha1 = chat_build.load_clip("raw/llm-chats/a.md", str(kb_root))
    assert fm.get("source") == "https://example.org/c/1" and turns and len(sha1) == 40


@pytest.mark.parametrize("key", ["../outside.md", "/etc/hosts", "raw/../outside.md", "raw//a.md"])
def test_chat_build_cannot_read_outside_raw(kb_root, key):
    with pytest.raises(StorageError):
        chat_build.load_clip(key, str(kb_root))


def test_digest_many_select_ignores_pages_whose_raw_is_missing_or_escapes(kb_root, monkeypatch):
    (kb_root / "raw" / "web-clips").mkdir()
    (kb_root / "raw" / "web-clips" / "ok.md").write_text("x")
    pages = [{"slug": s, "type": "blog-post", "depth": "easy", "raw": r, "url": ""} for s, r in
             [("ok", "raw/web-clips/ok.md"), ("gone", "raw/web-clips/gone.md"), ("up", "../outside.md"),
              ("abs", str(kb_root / "outside.md"))]]
    monkeypatch.setattr(digest_many, "ROOT", str(kb_root))
    monkeypatch.setattr(digest_many, "page_index", lambda: pages)
    assert digest_many.select() == ["raw/web-clips/ok.md"]


def test_export_bundles_raw_files_through_the_connector(kb_root, monkeypatch):
    (kb_root / "raw" / "printed-docs").mkdir()
    (kb_root / "raw" / "printed-docs" / "paper.pdf").write_bytes(b"%PDF-1")
    (kb_root / "raw" / ".DS_Store").write_bytes(b"junk")
    monkeypatch.setattr(export, "ROOT", str(kb_root))
    monkeypatch.setattr(export, "EXPORT_DIR", str(kb_root / ".exported"))
    monkeypatch.setattr(export, "TEXT_GLOBS", ())
    monkeypatch.setattr(export, "TEXT_ROOT_FILES", ())
    monkeypatch.setattr(export, "TEXT_META_FILES", ())
    monkeypatch.setattr(export, "BINARY_SUFFIXES", {".png"})
    assert export._collect_files(False) == []
    files = export._collect_files(True)
    assert "raw/printed-docs/paper.pdf" in files and "raw/.DS_Store" not in files
    archive = export.create_export(include_raw_pdfs=True, lint_first=False, stamp="t")
    with zipfile.ZipFile(archive) as zf:
        assert zf.read("raw/printed-docs/paper.pdf") == b"%PDF-1"


def test_the_connector_the_modules_use_refuses_escaping_keys(kb_root):
    store = for_kb(root=str(kb_root))
    for key in ("../outside.md", "/etc/hosts"):
        with pytest.raises(StorageError):
            store.get(key)
    assert not any("outside" in k for k in store.list("raw/"))
    assert os.path.exists(kb_root / "outside.md")


def test_exists_is_true_for_files_only_and_does_not_read_them(kb_root, monkeypatch):
    store = for_kb(root=str(kb_root))
    monkeypatch.setattr(type(store), "info", lambda *a, **k: pytest.fail("exists must not hash the file"))
    assert store.exists("raw/llm-chats/a.md")
    assert not store.exists("raw/llm-chats")
    assert not store.exists("raw/llm-chats/none.md")
