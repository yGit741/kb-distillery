"""The import layer contract (pyproject.toml [tool.importlinter]) holds. Skipped where import-linter (dev extra)
is not installed; `pixi run lint-imports` is the same check."""
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("importlinter")
ROOT = Path(__file__).resolve().parents[1]


def test_layer_contract_kept():
    r = subprocess.run([sys.executable, "-c", "from importlinter.cli import lint_imports_command as m; m()", "--no-cache"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]
