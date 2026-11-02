"""Layer contract: `lint` sits below `services`, so importing lint.lint and running its relations check (which
reads the kb's edge config from kb_distillery.graph.model) must not pull in any services module. Run in a
subprocess so modules other tests imported do not mask a regression."""
import subprocess
import sys

CODE = (
    "import sys\n"
    "import kb_distillery.lint.lint as lint\n"
    "page = ('wiki/a.md', {'type': 'idea', 'layer': 'concept'}, '---\\ntype: idea\\nrelations:\\n- {to: b, kind: x}\\n---\\n')\n"
    "lint.check_relations({'a': page})\n"
    "bad = sorted(m for m in sys.modules if m == 'kb_distillery.services' or m.startswith('kb_distillery.services.'))\n"
    "assert not bad, bad\n"
)


def test_lint_imports_without_services():
    r = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
