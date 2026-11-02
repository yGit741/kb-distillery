"""Layer contract: the stages (ops, metrics) sit below `kb_distillery.publish`. They reach the configured publisher through
the port in `kb_distillery.hosting`, so asking for a publish, checking the site and snapshots, the nightly report's site
line and the D1 account lookup must not load `kb_distillery.publish` at all. Run in a subprocess so modules other tests
imported do not mask a regression."""
import os
import subprocess
import sys

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "examples", "demo")

CODE = (
    "import sys, tempfile\n"
    "from kb_distillery import hosting\n"
    "from kb_distillery.ops import core, hygiene, nightly_report\n"
    "from kb_distillery.metrics import d1\n"
    "tmp = tempfile.mkdtemp()\n"
    "core.share_autodeploy('test', tmp)\n"
    "hygiene.check_snapshots(tmp, None)\n"
    "hygiene.check_site(tmp, None)\n"
    "nightly_report.site_status(tmp)\n"
    "try:\n"
    "    d1._account()\n"
    "except hosting.PublishError:\n"
    "    pass\n"
    "bad = sorted(m for m in sys.modules if m == 'kb_distillery.publish' or m.startswith('kb_distillery.publish.'))\n"
    "assert not bad, bad\n"
)


def test_stages_reach_the_publisher_without_publish():
    env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT")}
    env.update(KB=DEMO, KB_PUBLISHER="none", KB_ENGINE_CONFIG="/nonexistent/engine.toml", KB_SHARE_AUTODEPLOY="0")
    r = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr or r.stdout
