"""Layer contract: the config layer (`kbconfig`, `paths`, `config/`) sits below the vault model. Resolving a kb's
kit-merged `[types]` and building the data paths must not pull in `kb_distillery.vault` or `kb_distillery.vault`.
Run in a subprocess so modules other tests imported do not mask a regression."""
import os
import subprocess
import sys

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "examples", "demo")

CODE = (
    "import sys\n"
    "from kb_distillery import kbconfig, paths\n"
    "cfg = kbconfig.load_dir(sys.argv[1])\n"
    "assert cfg.kit == 'base', cfg.kit\n"
    "assert cfg.section('types'), 'kit types not merged'\n"
    "assert paths.WIKI_PATH and paths.MANIFEST_PATH and paths.OPS_PATH\n"
    "bad = sorted(m for m in sys.modules if m.split('.')[:2] == ['kb_distillery', 'vault'])\n"
    "assert not bad, bad\n"
)


def test_config_layer_imports_without_the_vault_model():
    env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT")}
    env["KB"] = DEMO
    r = subprocess.run([sys.executable, "-c", CODE, DEMO], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr or r.stdout
