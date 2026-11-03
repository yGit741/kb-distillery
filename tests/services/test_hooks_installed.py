"""Lifecycle 'hooks installed' follows what git really runs."""
import os
import subprocess
import tempfile
import unittest

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def g(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=dict(os.environ, **ENV))


class HooksInstalledTests(unittest.TestCase):
    """The Lifecycle 'hooks installed' flag follows what git really runs, not one fixed hooksPath string."""

    def _kit(self, d, executable=True):
        kit = os.path.join(d, "kit")
        os.makedirs(kit)
        for n in ("pre-commit", "commit-msg", "pre-push"):
            p = os.path.join(kit, n)
            open(p, "w").write("#!/bin/sh\n")
            os.chmod(p, 0o755 if executable else 0o644)
        return kit

    def test_absolute_and_relative_paths_count_when_executable(self):
        from kb_distillery.services.lifecycle import hooks_installed
        with tempfile.TemporaryDirectory() as d:
            kit = self._kit(d)
            repo = os.path.join(d, "kbs", "a")
            os.makedirs(repo)
            g(repo, "init", "-q")
            self.assertFalse(hooks_installed(repo))
            g(repo, "config", "core.hooksPath", kit)
            self.assertTrue(hooks_installed(repo))
            g(repo, "config", "core.hooksPath", os.path.relpath(kit, repo))
            self.assertTrue(hooks_installed(repo))
            g(repo, "config", "core.hooksPath", os.path.join(d, "missing"))
            self.assertFalse(hooks_installed(repo))

    def test_non_executable_hooks_do_not_count(self):
        from kb_distillery.services.lifecycle import hooks_installed
        with tempfile.TemporaryDirectory() as d:
            kit = self._kit(d, executable=False)
            repo = os.path.join(d, "r")
            os.makedirs(repo)
            g(repo, "init", "-q")
            g(repo, "config", "core.hooksPath", kit)
            self.assertFalse(hooks_installed(repo))
