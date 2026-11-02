"""The qmd node tools (scripts/qmd/*.mjs) get their knowledge base only from `python -m kb_distillery.kbconfig root`, via
scripts/qmd/with-kb.sh or scripts/launch.sh — never from where their file lives. Before this, both tools fell back
to the explorer checkout, so after the kb split the vector store and the search index were built (and read) in
a folder that is not a vault. These tests run the real chain: --kb → kbconfig → $KB_ROOT → kbroot.mjs."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from kb_distillery import paths
from kb_distillery import kbconfig

QMD = os.path.join(kbconfig.checkout_root(), "scripts", "qmd")
NODE = shutil.which("node")
MINIMAL = '[kb]\nid = "{id}"\nname = "Probe"\nschema_version = "1.6"\n'


def _node_ok():
    if not NODE:
        return False
    out = subprocess.run([NODE, "-p", "process.versions.node.split('.')[0]"], capture_output=True, text=True)
    return out.returncode == 0 and int(out.stdout.strip() or 0) >= 22


def _qmd_scripts():
    return sorted(os.path.join(QMD, f) for f in os.listdir(QMD) if f.endswith(".mjs"))


class SourceGuards(unittest.TestCase):
    """Cheap static checks so a new tool cannot bring the checkout fallback back."""

    def test_no_qmd_tool_derives_the_vault_from_its_own_location(self):
        for f in _qmd_scripts():
            src = open(f, encoding="utf-8").read()
            self.assertNotRegex(src, r"process\.env\.KB_ROOT\s*\|\|", f"{f}: KB_ROOT must not have a fallback")
            self.assertFalse("import.meta.url" in src and '"../.."' in src,
                             f"{f}: resolves a root from its own file location — use kbroot.mjs")

    def test_qmd_tools_that_touch_the_cache_use_kbroot(self):
        for f in _qmd_scripts():
            if os.path.basename(f) == "kbroot.mjs":
                continue
            src = open(f, encoding="utf-8").read()
            if ".cache" in src:
                self.assertIn('from "./kbroot.mjs"', src, f"{f}: reads .cache without kbroot.mjs")

    def test_pixi_tasks_and_launcher_hand_node_the_kb(self):
        pixi = open(os.path.join(kbconfig.checkout_root(), "pixi.toml"), encoding="utf-8").read()
        for line in pixi.splitlines():
            if re.search(r"scripts/qmd/\w+\.mjs", line):
                self.assertIn("scripts/qmd/with-kb.sh", line, f"pixi task runs a qmd tool without the kb: {line}")
        launch = open(os.path.join(kbconfig.checkout_root(), "scripts", "launch.sh"), encoding="utf-8").read()
        for line in launch.splitlines():
            if "scripts/qmd/" in line and "node " in line and not line.lstrip().startswith("#"):
                self.assertIn('KB_ROOT="$KB_ROOT_DIR"', line, f"launch.sh starts a qmd tool without the kb: {line}")


@unittest.skipUnless(_node_ok(), "node >= 22 not installed")
class Chain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bases = os.path.join(self.tmp, "kbs")
        self.kb = self._kb("vecprobe")
        self.probe = os.path.join(self.tmp, "probe.mjs")
        with open(self.probe, "w", encoding="utf-8") as f:
            f.write(f'import {{ kbRoot }} from "file://{os.path.join(QMD, "kbroot.mjs")}";\n'
                    "try { console.log(kbRoot()); } catch (e) { console.error(e.message); process.exit(1); }\n")

    def _kb(self, kb_id):
        root = os.path.join(self.bases, kb_id)
        os.makedirs(root)
        with open(os.path.join(root, "kb.toml"), "w", encoding="utf-8") as f:
            f.write(MINIMAL.format(id=kb_id))
        return os.path.realpath(root)

    def _env(self, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT")}
        env.update(KB_BASES_DIR=self.bases, PYTHONPATH=os.path.join(kbconfig.checkout_root(), "src"),
                   PATH=os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", ""))
        env.update(extra)
        return env

    def _with_kb(self, *args, **env):
        return subprocess.run(["bash", os.path.join(QMD, "with-kb.sh"), self.probe, *args], cwd=kbconfig.checkout_root(),
                              capture_output=True, text=True, env=self._env(**env))

    def test_kb_flag_resolves_to_the_kb_folder(self):
        out = self._with_kb("--kb", "vecprobe")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), self.kb)

    def test_kb_env_resolves_to_the_kb_folder(self):
        out = self._with_kb(KB="vecprobe")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), self.kb)

    def test_explicit_kb_root_wins(self):
        other = self._kb("other")
        out = self._with_kb("--kb", "vecprobe", KB_ROOT=other)
        self.assertEqual(out.stdout.strip(), other, out.stderr)

    def test_unknown_kb_fails_instead_of_falling_back(self):
        out = self._with_kb("--kb", "no-such-kb")
        self.assertNotEqual(out.returncode, 0)
        self.assertNotIn(os.path.realpath(kbconfig.checkout_root()), out.stdout)

    def test_kbroot_refuses_without_kb_root(self):
        out = subprocess.run([NODE, self.probe], capture_output=True, text=True, env=self._env())
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("KB_ROOT is not set", out.stderr)

    def test_kbroot_refuses_a_folder_that_is_not_a_kb(self):
        out = subprocess.run([NODE, self.probe], capture_output=True, text=True,
                             env=self._env(KB_ROOT=os.path.join(self.tmp, "empty")))
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("is not a knowledge base", out.stderr)


class KbconfigRoot(unittest.TestCase):
    def test_root_prints_the_vault(self):
        out = subprocess.run([sys.executable, "-m", "kb_distillery.kbconfig", "root"], capture_output=True, text=True,
                             env=dict(os.environ, PYTHONPATH=os.path.join(kbconfig.checkout_root(), "src")))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(os.path.realpath(out.stdout.strip()), os.path.realpath(paths.ROOT))


if __name__ == "__main__":
    unittest.main()
