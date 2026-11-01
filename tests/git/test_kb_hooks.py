"""The hooks a knowledge base repo runs: env.sh finds the engine at ../.., git honours a relative core.hooksPath,
and install-kb-hooks.sh writes what hooks_path_for says."""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from kb_distillery import kbconfig

ENGINE = kbconfig.CHECKOUT_ROOT
ENV_SH = os.path.join(ENGINE, "scripts", "kb-hooks", "env.sh")
INSTALL = os.path.join(ENGINE, "scripts", "install-kb-hooks.sh")
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _run(args, cwd, env=None, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env or GIT_ENV, check=False, **kw)


def _init_repo(path):
    os.makedirs(path, exist_ok=True)
    _run(["git", "init", "-q", "-b", "main"], path)
    _run(["git", "config", "user.name", "t"], path)
    _run(["git", "config", "user.email", "t@t"], path)


class FakeEngine(unittest.TestCase):
    """<tmp>/engine/{src/kb_distillery, scripts/kb-hooks} with a kb repo at <tmp>/engine/kbs/x."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.engine = os.path.join(self.tmp, "engine")
        os.makedirs(os.path.join(self.engine, "src", "kb_distillery"))
        os.makedirs(os.path.join(self.engine, "scripts", "kb-hooks"))
        self.kb = os.path.join(self.engine, "kbs", "x")
        _init_repo(self.kb)

    def _source_env(self, **extra):
        env = {**GIT_ENV, **extra}
        env.pop("KBD_DIR", None)
        env.update(extra)
        return _run(["bash", "-c", f'. "{ENV_SH}"; echo "$engine|$KB_ROOT|$KBD_DIR"'], self.kb, env=env)


class EnvShTests(FakeEngine):
    def test_engine_is_two_levels_above_the_kb(self):
        cp = self._source_env()
        self.assertEqual(cp.returncode, 0, cp.stderr)
        engine, kb_root, kbd_dir = cp.stdout.strip().split("|")
        self.assertEqual((os.path.realpath(engine), os.path.realpath(kb_root), os.path.realpath(kbd_dir)),
                         (self.engine, self.kb, self.engine))

    def test_kbd_dir_overrides(self):
        other = os.path.join(self.tmp, "other-engine")
        os.makedirs(os.path.join(other, "src", "kb_distillery"))
        cp = self._source_env(KBD_DIR=other)
        self.assertEqual(os.path.realpath(cp.stdout.split("|")[0]), other, cp.stderr)

    def test_missing_engine_fails_loudly_and_names_the_override(self):
        outside = os.path.join(self.tmp, "loose", "kb")           # ../.. is not an engine
        _init_repo(outside)
        cp = _run(["bash", "-c", f'. "{ENV_SH}"; echo reached'], outside)
        self.assertEqual(cp.returncode, 1)
        self.assertNotIn("reached", cp.stdout)
        self.assertIn("KBD_DIR", cp.stderr)

    def test_no_trace_of_the_old_names(self):
        with open(ENV_SH, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("KB_EXPLORER_DIR", text)
        self.assertNotIn("knowledge-base-explorer", text)


class RelativeHooksPathTests(FakeEngine):
    def _hook(self, exit_code):
        hook = os.path.join(self.engine, "scripts", "kb-hooks", "commit-msg")
        with open(hook, "w", encoding="utf-8") as f:
            f.write(f"#!/bin/bash\necho hook-ran >&2\nexit {exit_code}\n")
        os.chmod(hook, os.stat(hook).st_mode | stat.S_IXUSR)

    def test_git_runs_the_hook_through_a_relative_path_and_it_can_reject(self):
        self._hook(1)
        _run(["git", "config", "core.hooksPath", "../../scripts/kb-hooks"], self.kb)
        cp = _run(["git", "commit", "--allow-empty", "-q", "-m", "x"], self.kb)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("hook-ran", cp.stderr)

    def test_survives_renaming_the_engine_folder(self):
        self._hook(0)
        _run(["git", "config", "core.hooksPath", "../../scripts/kb-hooks"], self.kb)
        renamed = os.path.join(self.tmp, "kb-distillery")
        os.rename(self.engine, renamed)
        cp = _run(["git", "commit", "--allow-empty", "-q", "-m", "x"], os.path.join(renamed, "kbs", "x"))
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("hook-ran", cp.stderr)


class InstallScriptTests(unittest.TestCase):
    def test_installs_claude_hooks_and_an_absolute_path_for_a_kb_outside_kbs(self):
        tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        kb = os.path.join(tmp, "notes")
        _init_repo(kb)
        with open(os.path.join(kb, "kb.toml"), "w", encoding="utf-8") as f:
            f.write('[kb]\nid = "notes"\nname = "Notes"\nschema_version = "1.4"\n')
        env = {**GIT_ENV, "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ["PATH"],
               "PYTHONPATH": os.path.join(ENGINE, "src")}
        for k in ("KB", "KB_ROOT", "KB_BASES_DIR"):
            env.pop(k, None)
        cp = _run(["bash", INSTALL, "--kb", kb], ENGINE, env=env)
        self.assertEqual(cp.returncode, 0, cp.stderr + cp.stdout)
        for name in ("env.sh", "kb-guard.sh", "kb-git-guard.sh"):
            self.assertTrue(os.path.isfile(os.path.join(kb, ".claude", "hooks", name)), name)
        self.assertTrue(os.path.isfile(os.path.join(kb, ".claude", "settings.json")))
        hooks_path = _run(["git", "config", "core.hooksPath"], kb).stdout.strip()
        self.assertEqual(hooks_path, os.path.join(os.path.realpath(kbconfig.primary_root()), "scripts", "kb-hooks"))
        self.assertTrue(os.path.isabs(hooks_path))


if __name__ == "__main__":
    unittest.main()
