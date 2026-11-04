"""launch: --no-open / --port accepted in the checkout script and the wheel path, no bare `python`; qmd makes its db folder."""
import os
import re
import subprocess
import sys
from pathlib import Path

from kb_distillery.cli import tree

REPO = Path(__file__).resolve().parents[2]


def _stub(tmp_path):
    stub = tmp_path / "py"
    stub.write_text("#!/bin/sh\necho stub-stop >&2\nexit 1\n")           # stops launch.sh right after argument parsing
    stub.chmod(0o755)
    return stub


def test_launch_script_accepts_no_open_and_port_forms(tmp_path):
    for args in (["--no-open"], ["--port", "8999", "--no-open"], ["--port=8999", "--no-open"]):
        got = subprocess.run(["bash", str(REPO / "scripts/launch.sh"), *args], capture_output=True, text=True,
                             env=dict(os.environ, KB_PYTHON=str(_stub(tmp_path))))
        assert "unknown argument" not in got.stderr and "stub-stop" in got.stderr, got.stderr


def test_launch_script_has_no_bare_python():
    text = (REPO / "scripts/launch.sh").read_text()
    code = [l for l in text.splitlines() if not l.lstrip().startswith("#")]
    assert not [l for l in code if re.search(r"(^|[\s$(\"])python\s+-m\b", l)], "use the resolved interpreter"


def test_distill_launch_hands_its_interpreter_to_the_script(monkeypatch):
    seen = {}
    monkeypatch.setattr(tree, "repo_root", lambda: REPO)
    monkeypatch.setattr(tree, "require_repo_root", lambda prog: REPO)
    monkeypatch.delenv("KB_PYTHON", raising=False)
    monkeypatch.setattr(tree.subprocess, "call", lambda argv, env=None: seen.update(argv=argv, env=env) or 0)
    assert tree.main(["launch", "--no-open"]) == 0
    assert seen["env"]["KB_PYTHON"] == sys.executable and "--no-open" in seen["argv"]


def test_distill_launch_from_a_wheel_serves_with_the_port_and_no_open(monkeypatch):
    seen = {}
    monkeypatch.setattr(tree, "repo_root", lambda: None)
    monkeypatch.setattr(tree.runpy, "run_module", lambda target, **k: seen.update(target=target, argv=list(sys.argv)))
    for extra in ([], ["--port=9001"]):
        assert tree.main(["launch", "--no-open", *extra]) == 0
        assert seen["target"] == "kb_distillery.server" and "--no-open" in seen["argv"]
        assert sum(a.startswith("--port") or a == "--port" for a in seen["argv"]) == 1


def test_qmd_server_creates_the_index_folder_before_opening_the_db():
    text = (REPO / "scripts/qmd/server.mjs").read_text()
    mk = text.index('fs.mkdirSync(path.join(CACHE, "qmd")')
    assert mk < text.index('path.join(CACHE, "qmd", "index.sqlite")')
