"""Layer contract: `kb_distillery.llm` sits below `ingest`, so importing it (and building its TLS context) must not pull
`kb_distillery.ingest` in. Run in a subprocess so modules other tests imported do not mask a regression."""
import subprocess
import sys

CODE = (
    "import sys\n"
    "import kb_distillery.llm as llm\n"
    "llm._ssl()\n"
    "bad = sorted(m for m in sys.modules if m == 'kb_distillery.ingest' or m.startswith('kb_distillery.ingest.'))\n"
    "assert not bad, bad\n"
)


def test_llm_imports_without_ingest():
    r = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
