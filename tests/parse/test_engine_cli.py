"""The MinerU engine's command line, the windowed / resumable runner and the CLI, all with a fake engine."""
import json
import os

import pytest

from kb_distillery.parse import cli, run, sample
from kb_distillery.parse.engines import mineru

from . import pdfs


class FakeEngine:
    name = "fake"

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def parse(self, pdf, pages, workdir):
        self.calls.append(list(pages))
        if self.fail_on in pages:
            raise RuntimeError("boom")
        return {p: {"page_idx": p - 1, "text": "page %d" % p} for p in pages}

    def markdown(self, rec):
        return rec["text"]

    def figures(self, rec, width, height):
        return []


def test_parse_pages_and_windows():
    assert run.parse_pages("1-3, 7,2") == [1, 2, 3, 7]
    assert run.parse_pages("all", 4) == [1, 2, 3, 4]
    for bad in ("0", "5-2", "x", ""):
        with pytest.raises(ValueError):
            run.parse_pages(bad)
    with pytest.raises(ValueError):
        run.parse_pages("9", 4)
    assert run.windows([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_run_is_windowed_and_resumes_per_page(tmp_path):
    out = str(tmp_path / "o")
    eng = FakeEngine(fail_on=5)
    with pytest.raises(RuntimeError):
        run.run(eng, "x.pdf", [1, 2, 3, 4, 5, 6], out, window=2, log=lambda *_: None)
    assert eng.calls == [[1, 2], [3, 4], [5, 6]]
    assert run.done_pages(out, "fake") == [1, 2, 3, 4]                      # finished windows are kept
    assert open(run.md_path(out, 3)).read() == "page 3"
    eng2 = FakeEngine()
    res = run.run(eng2, "x.pdf", [1, 2, 3, 4, 5, 6], out, window=2, log=lambda *_: None)
    assert eng2.calls == [[5, 6]] and res["skipped"] == [1, 2, 3, 4] and res["parsed"] == [5, 6]
    st = run.status(out, "fake", [1, 2, 3, 4, 5, 6, 7])
    assert st["missing"] == [7] and st["seconds_per_page"] is not None
    run.run(eng2, "x.pdf", [1], out, window=2, force=True, log=lambda *_: None)
    assert eng2.calls[-1] == [1]


def test_mineru_command_is_local_only_and_windowed(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_MINERU_HOME", str(tmp_path / "m"))
    cmd = mineru.command("/a/b.pdf", "/o", [163, 170, 171, 172, 640])
    assert cmd[1:3] == ["parse", "/a/b.pdf"] and cmd[0].startswith(str(tmp_path / "m"))
    assert cmd[cmd.index("-p") + 1] == "163,170-172,640"
    assert cmd[cmd.index("--tier") + 1] == "advanced" and cmd[cmd.index("-f") + 1] == "middle_json"
    assert "--disable-image-analysis" in cmd
    assert not any(a.startswith("--remote") or a == "--api-key" for a in cmd)


def test_mineru_environment_is_private_and_telemetry_off(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_MINERU_HOME", str(tmp_path / "m"))
    env = mineru.environment({"PATH": "/bin", "HOME": "/Users/real", "HF_TOKEN": "secret", "OPENAI_API_KEY": "k"})
    assert env["HOME"] == env["HF_HOME"] == str(tmp_path / "m" / "home")
    assert env["MINERU_TELEMETRY_DISABLED"] == "1"
    assert "HF_TOKEN" not in env and "OPENAI_API_KEY" not in env and "/Users/real" not in env.values()


def test_mineru_missing_install_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_MINERU_HOME", str(tmp_path / "none"))
    from kb_distillery.parse.engines import EngineError
    with pytest.raises(EngineError, match="mineru-kit not found"):
        mineru.MinerU().parse("x.pdf", [1], str(tmp_path))


def test_stratify_is_seeded_covers_cells_and_splits_60_40():
    types = {p: ("figure" if p % 7 == 0 else "math" if p % 3 == 0 else "prose") for p in range(1, 401)}
    a = sample.stratify(types, 100, seed=7)
    assert a == sample.stratify(types, 100, seed=7) and a != sample.stratify(types, 100, seed=8)
    assert len(a["build"]) == 60 and len(a["unseen"]) == 40 and not set(a["build"]) & set(a["unseen"])
    picked = a["build"] + a["unseen"]
    assert len(set(picked)) == 100
    assert {types[p] for p in a["unseen"]} == {"figure", "math", "prose"}      # the holdout covers every type
    assert {(p - 1) * 10 // 400 for p in picked} == set(range(10))             # and every tenth of the book


def test_stratify_small_and_blank_pages():
    assert sample.stratify({1: "blank", 2: "blank"})["build"] == []
    s = sample.stratify({p: "prose" for p in range(1, 6)}, 100)
    assert sorted(s["build"] + s["unseen"]) == [1, 2, 3, 4, 5]


def test_cli_run_status_check_and_out_guard(tmp_path, monkeypatch, capsys):
    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(pdfs.build())
    monkeypatch.setattr(cli, "_engine", lambda name: FakeEngine())
    out = str(tmp_path / "out")
    assert cli.main(["run", str(pdf), "--pages", "1-2", "--out", out, "--engine", "fake"]) == 0
    assert json.loads(capsys.readouterr().out)["parsed"] == 2
    assert cli.main(["status", "--out", out, "--engine", "fake"]) == 0
    assert json.loads(capsys.readouterr().out)["done"] == [1, 2]
    assert cli.main(["check", str(pdf), "--out", out, "--engine", "fake"]) == 0
    text = capsys.readouterr().out
    assert "page 1:" in text and "flags per page" in text                       # fake text is not the page: flagged
    with pytest.raises(SystemExit):
        cli.main(["run", str(pdf), "--out", out])                                # no --pages
    with pytest.raises(SystemExit):
        cli._guard_out(str(tmp_path / "knowledge" / "kb" / "meta" / "parsed"))


# ---- MinerU middle-JSON -> Markdown (a record in the shape mineru-kit 4.1.3 writes; no MinerU runs here)

REC = {"page_idx": 4, "blocks": [
    {"type": "header", "content": [{"type": "text", "content": "CHAPTER 5. SINKS"}]},
    {"type": "paragraph_title", "level": 2, "content": [{"type": "text", "content": "5.1 Setup"}]},
    {"type": "text", "content": [{"type": "text", "content": "Let "}, {"type": "equation_inline", "content": "n \\in \\mathbb { N }"},
                                 {"type": "text", "content": " hold iff "},
                                 {"type": "equation_inline", "content": "--- e.g. $x$ -"}]},
    {"type": "equation", "content": "a = b \\tag {5.1}"},
    {"type": "image", "content": [{"type": "image_body", "bbox": [0.2, 0.5, 0.8, 0.7], "content": ""},
                                  {"type": "image_caption", "content": [{"type": "text", "content": "Figure 5.1: A plot."}]}]},
    {"type": "table", "content": [{"type": "table_caption", "content": [{"type": "text", "content": "Table 5.1: Cells."}]},
                                  {"type": "table_body", "content": "<table><tr><td>\\mathcal{F}_1</td><td>plain</td></tr></table>"}]},
]}


def test_to_markdown_shapes():
    md = mineru.to_markdown(REC)
    assert "CHAPTER 5. SINKS" in md                                          # running heads kept for the verifier
    assert "## 5.1 Setup" in md
    assert "Let $n \\in \\mathbb { N }$ hold iff $--- e.g. x -$" in md       # a stray $ would end the math early
    assert "$$\na = b \\tag {5.1}\n$$" in md
    assert "![](image)" in md and "Figure 5.1: A plot." in md and "Table 5.1: Cells." in md
    assert "<td>$\\mathcal{F}_1$</td><td>plain</td>" in md                   # raw LaTeX in a cell reads as math
    assert mineru.to_markdown({"blocks": []}) == "\n"


def test_figure_boxes_are_in_points():
    assert mineru.figure_boxes(REC, 600, 800) == [(120.0, 400.0, 480.0, 560.0)]


def test_tag_with_a_space_and_a_year_are_read_right():
    from kb_distillery.parse import structure
    assert structure.equation_tags("$$\na = b \\tag {13.52}\n$$") == ["13.52"]
    assert structure._layer_eq("Xiao et al. (2024)") == []
    assert structure._layer_eq("a = b (5.2)") == ["5.2"]
