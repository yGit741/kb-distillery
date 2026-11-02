"""Layer contract: `kb_distillery.core` sits below `lint` and `search`, so importing scopes and coherence (and running
the paths that used to import lazily upward) must not pull either in. Run in a subprocess so modules other tests
imported do not mask a regression."""
import subprocess
import sys
import tempfile

CODE = (
    "import sys\n"
    "import kb_distillery.core.scopes as scopes\n"
    "import kb_distillery.core.coherence as coherence\n"
    "try:\n"
    "    scopes.scope_context('scope-x', sys.argv[1])\n"
    "except scopes.ScopeUnknown:\n"
    "    pass\n"
    "coherence._regenerate()\n"
    "up = ('kb_distillery.lint', 'kb_distillery.search')\n"
    "bad = sorted(m for m in sys.modules if any(m == u or m.startswith(u + '.') for u in up))\n"
    "assert not bad, bad\n"
)


def test_core_imports_without_lint_or_search():
    with tempfile.TemporaryDirectory() as root:
        r = subprocess.run([sys.executable, "-c", CODE, root], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
