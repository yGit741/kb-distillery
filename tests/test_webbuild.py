"""The prebuilt web bundle: fetched from a file:// release dir, checksum-verified, unpacked atomically. No network."""
import hashlib
import io
import tarfile
from pathlib import Path

from kb_distillery import webbuild
from kb_distillery.webbuild import fetch_prebuilt


def make_release(tmp_path, version="1.2.3", files=None, sha=None, extra=None):
    rel = tmp_path / "release"
    rel.mkdir(exist_ok=True)
    files = {"index.html": "<html>new</html>", "assets/a.js": "x"} if files is None else files
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        if extra:
            extra(tf)
    blob = buf.getvalue()
    (rel / f"webapp-{version}.tar.gz").write_bytes(blob)
    (rel / f"webapp-{version}.sha256").write_text(f"{sha or hashlib.sha256(blob).hexdigest()}  webapp-{version}.tar.gz\n")
    return rel.as_uri()


def test_fetch_unpacks_and_marks_version(tmp_path):
    url = make_release(tmp_path)
    dest = tmp_path / "_webapp"
    assert fetch_prebuilt("1.2.3", dest, url=url) is True
    assert (dest / "index.html").read_text() == "<html>new</html>"
    assert (dest / "assets/a.js").is_file()
    assert (dest / "BUNDLE_VERSION").read_text().strip() == "1.2.3"
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []      # no temp dir left behind


def test_sha_mismatch_is_refused_and_dest_untouched(tmp_path):
    url = make_release(tmp_path, sha="0" * 64)
    dest = tmp_path / "_webapp"
    dest.mkdir()
    (dest / "index.html").write_text("old")
    assert fetch_prebuilt("1.2.3", dest, url=url) is False
    assert (dest / "index.html").read_text() == "old"


def test_missing_release_returns_false(tmp_path):
    assert fetch_prebuilt("9.9.9", tmp_path / "_webapp", url=(tmp_path / "nothing").as_uri()) is False
    assert not (tmp_path / "_webapp").exists()


def test_replaces_an_existing_dest_atomically(tmp_path):
    url = make_release(tmp_path)
    dest = tmp_path / "_webapp"
    dest.mkdir()
    (dest / "stale.txt").write_text("old")
    assert fetch_prebuilt("1.2.3", dest, url=url) is True
    assert not (dest / "stale.txt").exists() and (dest / "index.html").is_file()


def test_failed_unpack_keeps_the_old_dest(tmp_path):
    def evil(tf):
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    url = make_release(tmp_path, extra=evil)
    dest = tmp_path / "_webapp"
    dest.mkdir()
    (dest / "index.html").write_text("old")
    assert fetch_prebuilt("1.2.3", dest, url=url) is False
    assert (dest / "index.html").read_text() == "old" and not (tmp_path / "escape.txt").exists()


def test_bundle_without_index_is_refused(tmp_path):
    url = make_release(tmp_path, files={"other.txt": "x"})
    assert fetch_prebuilt("1.2.3", tmp_path / "_webapp", url=url) is False


def test_source_hash_gate(tmp_path):
    assert webbuild.bundle_matches_sources(tmp_path, "abc") is False         # no SOURCE_HASH recorded
    (tmp_path / "SOURCE_HASH").write_text("abc\n")
    assert webbuild.bundle_matches_sources(tmp_path, "abc") is True
    assert webbuild.bundle_matches_sources(tmp_path, "def") is False


def test_kb_web_bundle_zero_skips_the_fetch(tmp_path, monkeypatch):
    from kb_distillery.server import spa
    called = []
    monkeypatch.setattr(webbuild, "fetch_prebuilt", lambda *a, **k: called.append(a) or True)
    monkeypatch.setenv("KB_WEB_BUNDLE", "0")
    assert spa._try_prebuilt(tmp_path / "_webapp", "h") is False and called == []
    monkeypatch.setenv("KB_WEB_BUNDLE", "1")
    monkeypatch.setattr(webbuild, "installed_version", lambda: "1.2.3")
    assert spa._try_prebuilt(tmp_path / "_webapp", None) is True and len(called) == 1


def test_stale_bundle_falls_back_to_local_build(tmp_path, monkeypatch):
    from kb_distillery.server import spa

    url = make_release(tmp_path, files={"index.html": "bundle", "SOURCE_HASH": "other\n"})
    real = webbuild.fetch_prebuilt
    monkeypatch.setattr(webbuild, "fetch_prebuilt", lambda v, d, **k: real(v, d, url=url, **k))
    monkeypatch.setattr(webbuild, "installed_version", lambda: "1.2.3")
    monkeypatch.delenv("KB_WEB_BUNDLE", raising=False)
    dest = tmp_path / "_webapp"
    dest.mkdir()
    (dest / "index.html").write_text("my own build")
    assert spa._try_prebuilt(dest, "mine") is False
    assert (dest / "index.html").read_text() == "my own build"            # a mismatching bundle never replaces it
    assert spa._try_prebuilt(dest, "other") is True
    assert (dest / "index.html").read_text() == "bundle"
    assert (dest / spa.STAMP).read_text().strip() == "other"


def test_fetch_failure_never_raises(tmp_path):
    assert fetch_prebuilt("", tmp_path / "x") is False
    assert fetch_prebuilt("1.0.0", tmp_path / "x", url="http://127.0.0.1:1/none") is False
