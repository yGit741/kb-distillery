"""The import layer contract (pyproject.toml [tool.importlinter]) holds; `pixi run lint-imports` is the same check."""
import subprocess
import sys
from pathlib import Path

from kb_distillery.git import ship

ROOT = Path(__file__).resolve().parents[1]


def test_layer_contract_kept():
    r = subprocess.run([sys.executable, "-c", "from importlinter.cli import lint_imports_command as m; m()", "--no-cache"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]


def test_ship_runs_the_layer_contract_as_a_gate():
    assert "lint-imports" in dict(ship.GATES)
