"""Layer contract: `lint` is a pipeline stage and never imports an entry point (`kb_distillery.cli`, `kb_distillery.api`).
The skills linter checks `distill …` lines against the command table in `kb_distillery.config.commands`, and
`lint --dashboard` refuses instead of starting the app. Run in a subprocess so modules other tests imported do not
mask a regression."""
import os
import subprocess
import sys

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "examples", "demo")

CODE = (
    "import sys\n"
    "import kb_distillery.lint.lint_skills as ls\n"
    "ls.validate_cli_line('skills/x/SKILL.md', 'distill kb list')\n"
    "ls.validate_cli_line('skills/x/SKILL.md', 'distill nope')\n"
    "assert len(ls.errors) == 1 and 'unknown distill command: nope' in ls.errors[0], ls.errors\n"
    "import kb_distillery.lint.lint as lint\n"
    "sys.argv = ['lint', '--dashboard']\n"
    "assert lint.main() == 2\n"
    "top = ('kb_distillery.cli', 'kb_distillery.api')\n"
    "bad = sorted(m for m in sys.modules if m in top or m.startswith(tuple(t + '.' for t in top)))\n"
    "assert not bad, bad\n"
)


def test_lint_imports_no_entry_point():
    env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT")}
    env["KB"] = DEMO
    r = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr or r.stdout
    assert "pixi run app" in r.stderr
