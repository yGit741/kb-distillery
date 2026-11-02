"""Layer contract: `search.cypher` (the graph-query CLI the chat agent may run) sits below `services`. Building the live
graph snapshot, deciding on typed relations and running a query all live in `kb_distillery.graph`, so the CLI must not
load any services module. Run in a subprocess so modules other tests imported do not mask a regression."""
import os
import subprocess
import sys

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "examples", "demo")

CODE = (
    "import sys\n"
    "from kb_distillery.search import cypher\n"
    "assert cypher.main(['list']) == 0\n"
    "assert cypher.main(['run', 'MATCH (n) RETURN n.slug', '--limit', '3', '--json']) == 0\n"
    "from kb_distillery.graph import snapshot\n"
    "assert snapshot.build_graph_snapshot(layer='raw')['layer'] == 'raw'\n"
    "bad = sorted(m for m in sys.modules if m == 'kb_distillery.services' or m.startswith('kb_distillery.services.'))\n"
    "assert not bad, bad\n"
)


def test_cypher_cli_runs_without_services():
    env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT")}
    env["KB"] = DEMO
    r = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stderr or r.stdout
