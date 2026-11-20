"""kb-mcp read model on a temp kb: listing, search, pages, sources, what's new, and that nothing outside wiki/ leaks."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from kb_distillery.kb_mcp.library import KbMcpError, Library

KB_TOML = '[kb]\nid = "{id}"\nname = "{name}"\nschema_version = "1.5"\nkit = "base"\ndescription = "{desc}"\n'


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _make(base, kb_id, name, desc):
    root = str(base / kb_id)
    _w(f"{root}/kb.toml", KB_TOML.format(id=kb_id, name=name, desc=desc))
    _w(f"{root}/wiki/index.md", "# Wiki index\n\n- [Ideas](idea/index.md)\n")
    _w(f"{root}/wiki/idea/index.md", "# Ideas\n\n- [Tensor rank](tensor-rank.md)\n")
    _w(f"{root}/wiki/tensor-rank.md",
       "---\ntype: article\nlayer: source\nraw: raw/papers/tensor.md\ndescription: \"The minimal number of rank-one terms.\"\n"
       "sources:\n  - resource: https://example.com/tensor\n  - resource: /raw/papers/tensor.pdf\n---\n\n# Tensor rank\n\nRank-one decomposition notes.\n")
    _w(f"{root}/wiki/log.md", "# Log\n\n## 2099-01-02\n\n### digest | tensor paper ← `tensor-rank.md`\n\n## 2000-01-01\n\n### ingest | old entry\n")
    _w(f"{root}/raw/papers/tensor.md", "Tensor source text " + "x" * 50)
    _w(f"{root}/raw/papers/tensor.pdf", "%PDF binary")
    _w(f"{root}/think/secret.md", "# Secret think note about tensor rank\n")
    _w(f"{root}/meta/corpus.tsv", "# generated\npath\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n"
       "raw/papers/tensor.md\tabc\tpapers\tsource\ttensor-rank\t\t\nraw/papers/skip.md\tdef\tpapers\tskip\t\t\t\n")
    return root


@pytest.fixture
def lib(tmp_path, monkeypatch):
    bases = tmp_path / "bases"
    _make(bases, "alpha", "Alpha Notes", "Linear algebra and tensors")
    monkeypatch.setenv("KB_BASES_DIR", str(bases))
    monkeypatch.setenv("KB_APP_CONFIG", "/nonexistent/app.toml")
    monkeypatch.setenv("KB_SHARE_AUTODEPLOY", "0")
    other = tmp_path / "elsewhere"
    _make(other, "beta", "Beta Journal", "Cooking recipes")
    return Library([str(other / "beta")])


def test_list_kbs_has_metadata_from_both_sources(lib):
    kbs = {k["id"]: k for k in lib.list_kbs()["kbs"]}
    assert set(kbs) == {"alpha", "beta"}
    a = kbs["alpha"]
    assert (a["title"], a["pages"], a["sources"], a["kit"]) == ("Alpha Notes", 1, 1, "base")
    assert a["description"] == "Linear algebra and tensors" and a["last_change"]


def test_find_kb_ranks_by_words(lib):
    got = lib.find_kb("linear algebra tensor")["kbs"]
    assert got[0]["id"] == "alpha" and got[0]["best_pages"][0]["page"] == "tensor-rank.md"
    assert [k["id"] for k in lib.find_kb("cooking")["kbs"]] == ["beta"]


def test_search_hits_pages_only(lib):
    hits = lib.search("tensor rank")["hits"]
    assert {h["kb"] for h in hits} == {"alpha", "beta"}
    assert all(h["page"] == "tensor-rank.md" for h in hits), "no index.md, log.md, raw or think hits"
    assert hits[0]["description"] == "The minimal number of rank-one terms."
    assert [h["kb"] for h in lib.search("tensor", kb="beta")["hits"]] == ["beta"]
    assert "Secret" not in json.dumps(lib.search("secret"))


def test_search_falls_back_to_a_scan_when_the_index_is_unwritable(lib, monkeypatch):
    import sqlite3
    from kb_distillery.search import fts
    monkeypatch.setattr(fts, "search", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("readonly")))
    assert lib.search("rank-one", kb="alpha")["hits"][0]["page"] == "tensor-rank.md"


def test_get_index_root_and_section(lib):
    assert "[Ideas](idea/index.md)" in lib.get_index("alpha")
    assert "[Tensor rank](tensor-rank.md)" in lib.get_index("alpha", "idea")
    for bad in ("../raw", "nope", "idea/x"):
        with pytest.raises(KbMcpError):
            lib.get_index("alpha", bad)


def test_get_page_by_name_slug_title_and_refuses_the_rest(lib):
    for ref in ("tensor-rank.md", "tensor-rank", "Tensor rank", "wiki/tensor-rank.md"):
        assert "Rank-one decomposition notes." in lib.get_page("alpha", ref)
    for bad in ("../think/secret.md", "../raw/papers/tensor.md", "log.md", "index.md", "missing"):
        with pytest.raises(KbMcpError):
            lib.get_page("alpha", bad)
    with pytest.raises(KbMcpError, match="known: alpha, beta"):
        lib.get_page("nope", "x")
    assert lib.get_page("Alpha Notes", "tensor-rank")      # a kb is also found by its title


def test_get_sources_excerpt_and_metadata_only(lib):
    srcs = {s["resource"]: s for s in lib.get_sources("alpha", "tensor-rank.md")["sources"]}
    txt = srcs["raw/papers/tensor.md"]
    assert txt["kind"] == "raw" and txt["disposition"] == "source" and txt["excerpt"].startswith("Tensor source text")
    assert srcs["https://example.com/tensor"]["kind"] == "url"
    pdf = srcs["/raw/papers/tensor.pdf"]
    assert pdf["available"] and "excerpt" not in pdf, "a binary file is described, never served"
    short = lib.get_sources("alpha", "tensor-rank.md", max_chars=6)["sources"][0]
    assert short["excerpt"] == "Tensor" and short["truncated"]
    assert "excerpt" not in lib.get_sources("alpha", "tensor-rank.md", max_chars=0)["sources"][0]


def test_get_sources_never_leaves_raw(lib, tmp_path):
    _w(str(tmp_path / "bases/alpha/wiki/evil.md"), "---\nraw: raw/../think/secret.md\nsources:\n  - resource: /raw/../kb.toml\n---\n\n# Evil\n")
    for s in lib.get_sources("alpha", "evil.md")["sources"]:
        assert s["available"] is False and "excerpt" not in s


def test_whats_new_reads_log_entries_since_a_date(lib):
    got = lib.whats_new(kb="alpha")
    assert [(e["date"], e["op"], e["summary"]) for e in got["entries"]] == [("2099-01-02", "digest", "tensor paper")]
    assert len(lib.whats_new(since="1999-01-01", kb="alpha")["entries"]) == 2
    with pytest.raises(KbMcpError):
        lib.whats_new(since="yesterday")


def test_whats_new_falls_back_to_kb_commits(tmp_path, monkeypatch):
    root = _make(tmp_path / "bases", "gamma", "Gamma", "x")
    os.remove(f"{root}/wiki/log.md")
    monkeypatch.setenv("KB_BASES_DIR", str(tmp_path / "bases"))
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "kb(digest): add tensor paper (kb-1.5.2)"]):
        subprocess.run(["git", "-C", root, *cmd], check=True, env=env)
    e = Library().whats_new(since="2000-01-01", kb="gamma")["entries"][0]
    assert (e["op"], e["summary"], e["version"], e["source"]) == ("digest", "add tensor paper", "1.5.2", "git")
    assert Library().list_kbs()["kbs"][0]["last_change"]


def test_demo_kb_is_served(monkeypatch, tmp_path):
    demo = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "demo")
    monkeypatch.setenv("KB_BASES_DIR", str(tmp_path))
    work = tmp_path / "copy" / "demo"                 # a copy: the search index lands in the kb's .cache
    shutil.copytree(demo, work)
    lib = Library([str(work)])
    kb = lib.list_kbs()["kbs"][0]
    assert kb["id"] == "demo" and kb["pages"] > 10 and kb["sources"] >= 5
    assert lib.search("sensor fusion", kb="demo")["hits"]
    page = lib.get_page("demo", "process-acme-robotics")
    assert "Acme Robotics hiring process" in page
    assert lib.get_sources("demo", "posting-acme-senior-ml-engineer")["sources"][0]["path"] == "raw/web-clips/acme-senior-ml-engineer.md"


def test_never_writes_outside_the_search_cache(lib, tmp_path):
    before = {os.path.join(d, f) for d, _s, fs in os.walk(tmp_path) for f in fs}
    lib.search("tensor"); lib.find_kb("tensor"); lib.get_page("alpha", "tensor-rank"); lib.get_sources("alpha", "tensor-rank"); lib.whats_new()
    new = {p for d, _s, fs in os.walk(tmp_path) for f in fs for p in [os.path.join(d, f)]} - before
    assert all(os.sep + ".cache" + os.sep in p for p in new), new


def test_server_registers_the_seven_tools(lib):
    pytest.importorskip("mcp.server.mcpserver")
    import asyncio
    from kb_distillery.kb_mcp import server
    srv = server.build(lib)
    tools = asyncio.run(srv.list_tools())
    assert {t.name for t in tools} == {"list_kbs", "find_kb", "search", "get_index", "get_page", "get_sources", "whats_new"}
    out = asyncio.run(srv.call_tool("list_kbs", {}))
    assert "alpha" in str(out)


def test_cli_table_lists_mcp_and_help_runs():
    p = subprocess.run([sys.executable, "-m", "kb_distillery.kb_mcp", "--help"], capture_output=True, text=True,
                       env={**os.environ, "KB_APP_CONFIG": "/nonexistent/app.toml"})
    assert p.returncode == 0 and "usage: distill mcp" in p.stdout
    from kb_distillery.config.commands import COMMANDS
    assert COMMANDS["mcp"].target == "kb_distillery.kb_mcp"


def test_a_symlink_out_of_wiki_is_not_a_page(lib, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("# outside\n")
    os.symlink(outside, tmp_path / "bases/alpha/wiki/link.md")
    assert "link.md" not in [h["page"] for h in lib.search("outside", kb="alpha")["hits"]]
    with pytest.raises(KbMcpError):
        lib.get_page("alpha", "link.md")


def test_kb_flag_without_a_folder_is_an_error():
    from kb_distillery.kb_mcp.__main__ import _take_kbs
    with pytest.raises(SystemExit):
        _take_kbs(["--kb"])
    assert _take_kbs(["--kb", "/a", "--kb=/b"]) == ["/a", "/b"]
