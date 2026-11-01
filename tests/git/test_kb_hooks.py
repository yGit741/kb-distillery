"""The hooks a knowledge base repo runs (`kits/base/hooks`): each calls `distill hook <name>` with KB_ROOT set to its own
repo, none looks for an engine, all fail closed, git honours a relative core.hooksPath, `distill hooks install` writes
what hooks_path_for says, and the forwarding stubs of kbs wired before the move still run the kit hooks.

`distill` is always a fake on PATH here: the tests never run the real linter or guards."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from kb_distillery import kbconfig
from kb_distillery.config import resources
from kb_distillery.git import install_hooks

ENGINE = kbconfig.checkout_root()
KIT = os.path.join(ENGINE, "src", "kb_distillery", "kits", "base", "hooks")
GIT_HOOKS = ("pre-commit", "commit-msg", "pre-push")
CLAUDE_HOOKS = ("kb-guard.sh", "kb-git-guard.sh")
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _run(args, cwd, env=None, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env or GIT_ENV, check=False, **kw)


def _init_repo(path):
    os.makedirs(path, exist_ok=True)
    _run(["git", "init", "-q", "-b", "main"], path)
    _run(["git", "config", "user.name", "t"], path)
    _run(["git", "config", "user.email", "t@t"], path)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def fake_distill(self, exit_code=0):
        """A `distill` on PATH that logs its arguments, KB_ROOT, KB and stdin to <tmp>/log and exits `exit_code`."""
        bindir = os.path.join(self.tmp, "bin")
        os.makedirs(bindir, exist_ok=True)
        self.log = os.path.join(self.tmp, "log")
        path = os.path.join(bindir, "distill")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'#!/bin/bash\necho "args=$* KB_ROOT=$KB_ROOT KB=$KB PYTHONPATH=$PYTHONPATH" >> "{self.log}"\n'
                    f'cat >> "{self.log}"\nexit {exit_code}\n')
        os.chmod(path, 0o755)
        return bindir

    def env(self, bindir=None, **extra):
        env = {**GIT_ENV, "PATH": (bindir + os.pathsep if bindir else "") + os.environ["PATH"], **extra}
        env.pop("PYTHONPATH", None)
        return env

    def logged(self):
        with open(self.log, encoding="utf-8") as f:
            return f.read()


class KitHookFilesTests(unittest.TestCase):
    def test_every_hook_is_executable_and_names_no_engine(self):
        for name in (*GIT_HOOKS, *CLAUDE_HOOKS):
            path = os.path.join(KIT, name)
            self.assertTrue(os.stat(path).st_mode & stat.S_IXUSR, f"{name} is not executable (git would skip it)")
            tracked = subprocess.run(["git", "ls-files", "-s", name], cwd=KIT, capture_output=True, text=True).stdout
            self.assertTrue(tracked.startswith("100755"), f"{name}: git does not track the executable bit ({tracked!r})")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for retired in ("PYTHONPATH", "KBD_DIR", "backend" + "/src", "src/kb_distillery", ".pixi", "env.sh", "python -m", "python3"):
                self.assertNotIn(retired, text, f"{name} still names {retired}")
            self.assertIn("distill hook", text)
        self.assertFalse(os.path.exists(os.path.join(KIT, "env.sh")))

    def test_the_settings_call_the_wrappers_which_fail_closed(self):
        with open(os.path.join(KIT, "claude-settings.json"), encoding="utf-8") as f:
            commands = [h["command"] for g in json.load(f)["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertEqual(commands, [f'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/{n}"' for n in CLAUDE_HOOKS])

    def test_the_install_script_is_gone(self):
        self.assertFalse(os.path.exists(os.path.join(ENGINE, "scripts", "install-kb-hooks.sh")))


class GitHookTests(Tmp):
    def setUp(self):
        super().setUp()
        self.kb = os.path.join(self.tmp, "kb")
        _init_repo(self.kb)

    def test_each_git_hook_runs_distill_hook_with_its_own_repo_as_kb_root(self):
        bindir = self.fake_distill()
        for name in GIT_HOOKS:
            # KB names another kb on purpose: KB_ROOT (this repo) must win, or a hook would lint the wrong kb
            cp = _run(["bash", os.path.join(KIT, name), "arg1"], self.kb, env=self.env(bindir, KB="some-other-kb"))
            self.assertEqual(cp.returncode, 0, cp.stderr)
        log = self.logged()
        for name in GIT_HOOKS:
            self.assertIn(f"args=hook {name}", log)
        self.assertEqual(log.count(f"KB_ROOT={self.kb} "), 3, log)
        self.assertIn("hook commit-msg arg1", log)
        self.assertIn("hook pre-push arg1", log)
        self.assertNotIn("PYTHONPATH=/", log)

    def test_pre_push_hands_stdin_to_distill(self):
        bindir = self.fake_distill()
        cp = _run(["bash", os.path.join(KIT, "pre-push"), "origin", "url"], self.kb, env=self.env(bindir),
                  input="refs/heads/main abc refs/heads/main def\n")
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("refs/heads/main abc refs/heads/main def", self.logged())

    def test_a_failing_hook_fails_the_git_hook(self):
        bindir = self.fake_distill(exit_code=2)
        for name in GIT_HOOKS:
            cp = _run(["bash", os.path.join(KIT, name), "x"], self.kb, env=self.env(bindir))
            self.assertNotEqual(cp.returncode, 0, name)

    def test_pre_commit_skips_the_second_lint_on_the_one_time_token(self):
        bindir = self.fake_distill(exit_code=1)
        token = os.path.join(self.kb, ".git", "kb-linted")
        with open(token, "w", encoding="utf-8") as f:
            f.write("abc123\n")
        self.assertNotEqual(_run(["bash", os.path.join(KIT, "pre-commit")], self.kb, env=self.env(bindir)).returncode, 0)
        cp = _run(["bash", os.path.join(KIT, "pre-commit")], self.kb, env=self.env(bindir, KB_LINTED="abc123"))
        self.assertEqual(cp.returncode, 0, cp.stderr)
        cp = _run(["bash", os.path.join(KIT, "pre-commit")], self.kb, env=self.env(bindir, KB_LINTED="wrong"))
        self.assertEqual(cp.returncode, 1)
        self.assertIn("lint failed", cp.stderr)

    def test_a_missing_distill_blocks_and_names_the_fix(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        env = {**GIT_ENV, "PATH": empty}
        for name in GIT_HOOKS:
            cp = subprocess.run(["/bin/bash", os.path.join(KIT, name), "x"], cwd=self.kb, capture_output=True, text=True, env=env)
            self.assertEqual(cp.returncode, 2, name)
            self.assertIn("fail closed", cp.stderr)
            self.assertIn("PATH", cp.stderr)

    def test_git_blocks_the_commit_when_the_hook_fails_and_when_distill_is_missing(self):
        _run(["git", "config", "core.hooksPath", KIT], self.kb)
        bindir = self.fake_distill(exit_code=1)
        cp = _run(["git", "commit", "--allow-empty", "-q", "-m", "x"], self.kb, env=self.env(bindir))
        self.assertNotEqual(cp.returncode, 0)
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        git = shutil.which("git")
        cp = subprocess.run([git, "commit", "--allow-empty", "-q", "-m", "x"], cwd=self.kb, capture_output=True, text=True,
                            env={**GIT_ENV, "PATH": f"{empty}{os.pathsep}{os.path.dirname(git)}"})
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("fail closed", cp.stderr)


class ClaudeHookTests(Tmp):
    def setUp(self):
        super().setUp()
        self.kb = os.path.join(self.tmp, "kb")
        _init_repo(self.kb)

    def _run_hook(self, name, bindir=None, stdin="{}", **extra):
        env = self.env(bindir, CLAUDE_PROJECT_DIR=self.kb, **extra)
        if bindir is None:
            env["PATH"] = os.path.join(self.tmp, "empty")
        return subprocess.run(["/bin/bash", os.path.join(KIT, name)], cwd=self.tmp, capture_output=True, text=True, env=env, input=stdin)

    def test_the_wrapper_runs_the_guard_with_the_payload_and_this_kb(self):
        bindir = self.fake_distill()
        for name, hook in (("kb-guard.sh", "guard"), ("kb-git-guard.sh", "git-guard")):
            cp = self._run_hook(name, bindir, stdin='{"tool_input": {"command": "ls"}}', KB="some-other-kb")
            self.assertEqual(cp.returncode, 0, cp.stderr)
            self.assertIn(f"args=hook {hook} ", self.logged())
        self.assertIn(f"KB_ROOT={self.kb} ", self.logged())
        self.assertIn('"command": "ls"', self.logged())

    def test_every_failure_is_exit_2_because_claude_blocks_only_on_2(self):
        for name in CLAUDE_HOOKS:
            cp = self._run_hook(name)                                        # no distill on PATH
            self.assertEqual(cp.returncode, 2, name)
            self.assertIn("fail closed", cp.stderr)
            for code in (1, 127, 3):                                         # a crash or a missing interpreter inside distill
                self.assertEqual(self._run_hook(name, self.fake_distill(exit_code=code)).returncode, 2, (name, code))
            self.assertEqual(self._run_hook(name, self.fake_distill(exit_code=2)).returncode, 2)
        env = self.env(self.fake_distill(), CLAUDE_PROJECT_DIR=os.path.join(self.tmp, "gone"))
        cp = subprocess.run(["/bin/bash", os.path.join(KIT, "kb-guard.sh")], cwd=self.tmp, capture_output=True, text=True, env=env, input="{}")
        self.assertEqual(cp.returncode, 2)                                   # unknown project dir: deny, not allow


class RelativeHooksPathTests(Tmp):
    """<tmp>/engine/{src/kb_distillery/kits/base/hooks, kbs/x}: git honours the relative path and it survives a rename."""

    def setUp(self):
        super().setUp()
        self.engine = os.path.join(self.tmp, "engine")
        self.hooks = os.path.join(self.engine, "src", "kb_distillery", "kits", "base", "hooks")
        os.makedirs(self.hooks)
        self.kb = os.path.join(self.engine, "kbs", "x")
        _init_repo(self.kb)

    def _hook(self, exit_code):
        hook = os.path.join(self.hooks, "commit-msg")
        with open(hook, "w", encoding="utf-8") as f:
            f.write(f"#!/bin/bash\necho hook-ran >&2\nexit {exit_code}\n")
        os.chmod(hook, os.stat(hook).st_mode | stat.S_IXUSR)

    def test_git_runs_the_hook_through_a_relative_path_and_it_can_reject(self):
        self._hook(1)
        _run(["git", "config", "core.hooksPath", "../../src/kb_distillery/kits/base/hooks"], self.kb)
        cp = _run(["git", "commit", "--allow-empty", "-q", "-m", "x"], self.kb)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("hook-ran", cp.stderr)

    def test_survives_renaming_the_engine_folder(self):
        self._hook(0)
        _run(["git", "config", "core.hooksPath", "../../src/kb_distillery/kits/base/hooks"], self.kb)
        renamed = os.path.join(self.tmp, "kb-distillery")
        os.rename(self.engine, renamed)
        cp = _run(["git", "commit", "--allow-empty", "-q", "-m", "x"], os.path.join(renamed, "kbs", "x"))
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("hook-ran", cp.stderr)


class InstallTests(Tmp):
    def setUp(self):
        super().setUp()
        # a linked worktree wires kbs to the PRIMARY checkout's kit (it outlives the worktree), which does not hold a hook
        # added on this branch yet: pretend this checkout is the primary
        patcher = mock.patch.object(kbconfig, "primary_root", return_value=ENGINE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _kb(self, name="notes"):
        kb = os.path.join(self.tmp, name)
        _init_repo(kb)
        with open(os.path.join(kb, "kb.toml"), "w", encoding="utf-8") as f:
            f.write(f'[kb]\nid = "{name}"\nname = "Notes"\nschema_version = "1.4"\n')
        return kb

    def _kit_copy(self):
        kit = os.path.join(self.tmp, "kit", "kits", "base", "hooks")
        shutil.copytree(KIT, kit)
        return kit

    def test_installs_claude_hooks_and_the_kit_path_for_a_kb_outside_the_engine(self):
        kb = self._kb()
        with mock.patch("sys.stdout"):
            self.assertEqual(install_hooks.install(kb), 0)
        for name in CLAUDE_HOOKS:
            path = os.path.join(kb, ".claude", "hooks", name)
            self.assertTrue(os.stat(path).st_mode & stat.S_IXUSR, name)
        with open(os.path.join(kb, ".claude", "settings.json"), "rb") as a, open(os.path.join(KIT, "claude-settings.json"), "rb") as b:
            self.assertEqual(a.read(), b.read())
        hooks_path = _run(["git", "config", "core.hooksPath"], kb).stdout.strip()
        self.assertEqual(hooks_path, kbconfig.hooks_path_for(kb))
        self.assertTrue(os.path.isabs(hooks_path))
        self.assertTrue(hooks_path.endswith(os.path.join("kits", "base", "hooks")), hooks_path)
        for name in GIT_HOOKS:
            self.assertTrue(os.access(os.path.join(hooks_path, name), os.X_OK), name)
        self.assertFalse(os.path.exists(os.path.join(kb, ".claude", "hooks", "env.sh")))

    def test_a_second_install_backs_up_a_different_settings_file(self):
        kb = self._kb()
        os.makedirs(os.path.join(kb, ".claude"))
        with open(os.path.join(kb, ".claude", "settings.json"), "w", encoding="utf-8") as f:
            f.write('{"mine": 1}')
        with mock.patch("sys.stdout"):
            install_hooks.install(kb)
            install_hooks.install(kb)
        with open(os.path.join(kb, ".claude", "settings.json.bak"), encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"mine": 1}')

    def test_a_non_executable_git_hook_fails_the_install_instead_of_silently_skipping(self):
        kb = self._kb()
        kit = self._kit_copy()
        os.chmod(os.path.join(kit, "pre-commit"), 0o644)
        with mock.patch.object(resources, "resource", side_effect=lambda p: kit if p == "kits/base/hooks" else resources.package_root() / p), \
                mock.patch.object(kbconfig, "primary_root", return_value=None), mock.patch("sys.stdout"), mock.patch("sys.stderr") as err:
            self.assertEqual(install_hooks.install(kb), 1)
        self.assertIn("pre-commit", "".join(c.args[0] for c in err.write.call_args_list))

    def test_an_incomplete_kit_fails_the_install(self):
        kb = self._kb()
        kit = self._kit_copy()
        os.remove(os.path.join(kit, "pre-push"))
        with mock.patch.object(resources, "resource", side_effect=lambda p: kit if p == "kits/base/hooks" else resources.package_root() / p), \
                mock.patch("sys.stderr"):
            self.assertEqual(install_hooks.install(kb), 1)

    def test_a_folder_that_is_not_a_repo_gets_only_the_claude_hooks(self):
        kb = os.path.join(self.tmp, "plain")
        os.makedirs(kb)
        with mock.patch("sys.stdout"):
            self.assertEqual(install_hooks.install(kb), 0)
        self.assertTrue(os.path.isfile(os.path.join(kb, ".claude", "settings.json")))

    def test_distill_hooks_install_works_from_the_command_line_and_refuses_without_a_kb(self):
        from kb_distillery.cli import tree
        kb = self._kb()
        patcher = mock.patch.dict(sys.modules)      # runpy re-executes the module: drop the copy this file imported
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("kb_distillery.git.install_hooks", None)
        env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(kbconfig, "_current", False), \
                mock.patch.dict(os.environ, {"KB_BASES_DIR": os.path.join(self.tmp, "none")}), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr") as err:
            self.assertEqual(tree.main(["hooks", "install"]), 1)
            self.assertIn("no knowledge base selected", "".join(c.args[0] for c in err.write.call_args_list))
        with mock.patch.dict(os.environ, {**env, "KB": kb}, clear=True), mock.patch.object(kbconfig, "_current", False), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            self.assertEqual(tree.main(["hooks", "install"]), 0)
        self.assertEqual(_run(["git", "config", "core.hooksPath"], kb).stdout.strip(), kbconfig.hooks_path_for(kb))


class ForwardingStubTests(Tmp):
    """Stubs for a kb wired before the move (thesis: core.hooksPath ../../tools/kb-hooks): they run the kit hook through
    the engine they sit in, put the engine's pixi env first on PATH, and print the exact fix."""

    def _engine(self, folder):
        engine = os.path.join(self.tmp, "engine")
        kit = os.path.join(engine, "src", "kb_distillery", "kits", "base", "hooks")
        os.makedirs(kit)
        os.makedirs(os.path.join(engine, folder))
        hook = os.path.join(kit, "commit-msg")
        with open(hook, "w", encoding="utf-8") as f:
            f.write('#!/bin/bash\necho "kit-hook-ran $* PATH0=${PATH%%:*}"\n')
        os.chmod(hook, 0o755)
        for name in GIT_HOOKS:
            shutil.copy(os.path.join(ENGINE, folder, name), os.path.join(engine, folder, name))
        kb = os.path.join(engine, "kbs", "x")
        _init_repo(kb)
        _run(["git", "config", "core.hooksPath", f"../../{folder}"], kb)
        return engine, kit, kb

    def test_both_stub_folders_forward_and_print_the_fix(self):
        for folder in ("scripts/kb-hooks", "tools/kb-hooks"):
            with self.subTest(folder):
                shutil.rmtree(os.path.join(self.tmp, "engine"), ignore_errors=True)
                engine, kit, kb = self._engine(folder)
                msg = os.path.join(self.tmp, "msg")
                with open(msg, "w", encoding="utf-8") as f:
                    f.write("x\n")
                cp = _run(["bash", os.path.join(engine, folder, "commit-msg"), msg], kb)
                self.assertEqual(cp.returncode, 0, cp.stderr)
                self.assertIn("kit-hook-ran", cp.stdout)
                self.assertTrue(cp.stdout.strip().endswith(os.path.join(engine, ".pixi", "envs", "default", "bin")), cp.stdout)
                self.assertIn(f'git -C "{kb}" config core.hooksPath "{kit}"', cp.stderr)
                self.assertIn(f'distill hooks install --kb "{kb}"', cp.stderr)

    def test_a_stub_without_the_kit_fails_closed(self):
        engine, kit, kb = self._engine("scripts/kb-hooks")
        shutil.rmtree(kit)
        cp = _run(["bash", os.path.join(engine, "scripts/kb-hooks", "pre-commit")], kb)
        self.assertEqual(cp.returncode, 2)
        self.assertIn("fail closed", cp.stderr)

    def test_the_stubs_are_executable_and_tracked_as_such(self):
        for folder in ("scripts/kb-hooks", "tools/kb-hooks"):
            for name in GIT_HOOKS:
                self.assertTrue(os.access(os.path.join(ENGINE, folder, name), os.X_OK), f"{folder}/{name}")
        out = subprocess.run(["git", "ls-files", "-s", "scripts/kb-hooks", "tools/kb-hooks"], cwd=ENGINE, capture_output=True, text=True).stdout
        self.assertFalse([l for l in out.splitlines() if not l.startswith("100755")], out)


if __name__ == "__main__":
    unittest.main()


class ClaudeProjectDirTests(Tmp):
    def test_an_unset_project_dir_denies_and_a_kb_toml_folder_is_the_kb_root(self):
        bindir = self.fake_distill()
        kb = os.path.join(self.tmp, "outer", "kb")
        os.makedirs(kb)
        _init_repo(os.path.join(self.tmp, "outer"))
        with open(os.path.join(kb, "kb.toml"), "w", encoding="utf-8") as f:
            f.write("")
        for name in CLAUDE_HOOKS:
            env = self.env(bindir)
            env.pop("CLAUDE_PROJECT_DIR", None)
            cp = subprocess.run(["/bin/bash", os.path.join(KIT, name)], cwd=self.tmp, capture_output=True, text=True, env=env, input="{}")
            self.assertEqual(cp.returncode, 2, name)
            cp = subprocess.run(["/bin/bash", os.path.join(KIT, name)], cwd=self.tmp, capture_output=True, text=True,
                                env=self.env(bindir, CLAUDE_PROJECT_DIR=kb), input="{}")
            self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn(f"KB_ROOT={kb} ", self.logged())
