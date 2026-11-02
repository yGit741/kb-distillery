"""distill: the command tree (every subcommand's --help, dispatch to the module's main), the kbd alias and its mapping
table, the ~/.config migration stop, and that none of it needs a knowledge base.

Nothing here reads the real ~/.config: subprocesses and in-process calls run with HOME pointing at a temp folder. A
forwarded `--help` runs the target module, so only modules that parse `--help` themselves are forwarded (Cmd.forward_help);
the linter, for one, ignores it and would run.
"""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from kb_distillery import cli
from kb_distillery.cli import legacy, tree
from kb_distillery.config import userdir
from kb_distillery.config.resources import NotInCheckout

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")


def leaves(commands=None, trail=()):
    """(path, Cmd) for every runnable command, groups expanded."""
    for name, cmd in (tree.COMMANDS if commands is None else commands).items():
        if cmd.kind == "group":
            yield from leaves(cmd.sub, (*trail, name))
        else:
            yield (*trail, name), cmd


def _env(home, extra=None):
    env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT", "KB_BASES_DIR", "KB_DISTILLERY_HOME", "ANTHROPIC_API_KEY")}
    env.update(PYTHONPATH=SRC, HOME=home, KB_APP_CONFIG="/nonexistent/app.toml", KB_SHARE_AUTODEPLOY="0")
    env.update(extra or {})
    return env


def run_cli(args, home, extra=None, entry="kb_distillery.cli"):
    return subprocess.run([sys.executable, "-m", entry, *args], capture_output=True, text=True, env=_env(home, extra), check=False)


def call(fn, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fn(argv)
    return code, out.getvalue(), err.getvalue()


class TempHome(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.dict(os.environ, {"HOME": self.home})
        patcher.start()
        self.addCleanup(patcher.stop)

    def legacy_only(self):
        os.makedirs(os.path.join(self.home, ".config", "thesis-kb"))
        with open(os.path.join(self.home, ".config", "thesis-kb", "anthropic_key"), "w") as f:
            f.write("sk-test\n")


class CommandTableTests(unittest.TestCase):
    def test_every_target_exists(self):
        for path, cmd in leaves():
            name = " ".join(path)
            if cmd.kind == "module":
                self.assertIsNotNone(importlib.util.find_spec(cmd.target), f"{name}: no module {cmd.target}")
            elif cmd.kind == "script":
                self.assertTrue(os.path.isfile(os.path.join(ROOT, cmd.target)), f"{name}: no script {cmd.target}")
            else:
                self.assertEqual(cmd.kind, "launch")
                self.assertTrue(os.path.isfile(os.path.join(ROOT, cmd.target)), f"{name}: no script {cmd.target}")

    def test_every_command_says_what_it_does(self):
        for path, cmd in leaves():
            self.assertTrue(cmd.help.strip(), " ".join(path))

    def test_the_commands_of_the_plan_are_there(self):
        self.assertEqual(
            set(tree.COMMANDS),
            {"init", "doctor", "kb", "launch", "hooks", "hook", "ops", "ship", "ingest", "digest", "send", "lint", "llm", "share", "propose"})
        self.assertEqual(set(tree.COMMANDS["kb"].sub), {"list", "show"})
        self.assertEqual(set(tree.COMMANDS["hooks"].sub), {"install"})
        self.assertEqual(set(tree.COMMANDS["hook"].sub), {"guard", "git-guard", "pre-commit", "commit-msg", "pre-push"})

    def test_only_modules_that_parse_help_are_forwarded(self):
        # the linter and the digest focus print/write instead of parsing --help: never forward to them
        self.assertFalse(tree.COMMANDS["lint"].forward_help)
        self.assertFalse(tree.COMMANDS["digest"].sub["instructions"].forward_help)
        for path, cmd in leaves():
            if cmd.forward_help:
                self.assertEqual(cmd.kind, "module", " ".join(path))


class HelpTests(unittest.TestCase):
    def test_top_level_help_lists_every_visible_command(self):
        for argv in ([], ["--help"], ["-h"], ["help"]):
            code, out, _ = call(tree.main, argv)
            self.assertEqual(code, 0)
            for name in tree.visible():
                self.assertIn(name, out)

    def test_ship_is_listed_only_inside_a_checkout(self):
        with patch.object(tree, "repo_root", return_value=ROOT):
            self.assertIn("ship", call(tree.main, ["--help"])[1])
        with patch.object(tree, "repo_root", return_value=None):
            self.assertNotIn("ship", call(tree.main, ["--help"])[1].replace("relationship", ""))

    def test_help_for_every_command_and_group_in_process(self):
        # forward_help leaves are answered by their module (subprocess test below); everything else is answered here
        for path, cmd in leaves():
            if cmd.forward_help:
                continue
            code, out, _ = call(tree.main, [*path, "--help"])
            self.assertEqual(code, 0, path)
            self.assertIn("distill " + " ".join(path), out)
            self.assertIn(cmd.help.split()[0], out)
        for name, cmd in tree.COMMANDS.items():
            if cmd.kind == "group":
                code, out, _ = call(tree.main, [name, "--help"])
                self.assertEqual(code, 0, name)
                for sub in cmd.sub:
                    self.assertIn(sub, out)

    def test_help_word_form(self):
        code, out, _ = call(tree.main, ["help", "kb", "list"])
        self.assertEqual(code, 0)
        self.assertIn("distill kb list", out)

    def test_a_group_needs_a_subcommand_and_unknown_ones_exit_2(self):
        for argv, text in ((["kb"], "needs a subcommand"), (["kb", "nope"], "unknown subcommand"), (["nope"], "unknown command")):
            code, _, err = call(tree.main, argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(text, err)

    def test_forwarded_help_comes_from_the_module(self):
        with tempfile.TemporaryDirectory() as home:
            for path, cmd in leaves():
                if not cmd.forward_help:
                    continue
                cp = run_cli([*path, "--help"], home)
                self.assertEqual(cp.returncode, 0, f"{path}: {cp.stderr[-400:]}")
                self.assertIn("usage", cp.stdout.lower(), path)

    def test_help_needs_no_knowledge_base(self):
        with tempfile.TemporaryDirectory() as home:
            cp = run_cli(["--help"], home, {"KB_BASES_DIR": os.path.join(home, "no-such-dir")})
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("lint", cp.stdout)

    def test_importing_cli_does_not_load_kbconfig(self):
        cp = subprocess.run([sys.executable, "-c", "import sys, kb_distillery.cli; print('kb_distillery.kbconfig' in sys.modules)"],
                            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": SRC}, check=False)
        self.assertEqual(cp.stdout.strip(), "False", cp.stderr)


class DispatchTests(TempHome):
    def run_with_fake(self, argv, exit_code=None):
        seen = {}

        def fake(module, run_name, alter_sys):
            seen.update(module=module, argv=list(sys.argv), run_name=run_name)
            if exit_code is not None:
                raise SystemExit(exit_code)

        with patch.object(tree.runpy, "run_module", side_effect=fake), patch.object(sys, "argv", ["distill"]):
            code = tree.main(argv)
        return code, seen

    def test_hands_the_rest_of_the_line_to_the_module_and_returns_its_exit_code(self):
        code, seen = self.run_with_fake(["lint", "--health", "--kb", "demo"], exit_code=3)
        self.assertEqual(code, 3)
        self.assertEqual(seen["module"], "kb_distillery.lint.lint")
        self.assertEqual(seen["argv"], ["distill lint", "--health", "--kb", "demo"])
        self.assertEqual(seen["run_name"], "__main__")

    def test_each_command_runs_the_module_the_plan_names(self):
        cases = {
            ("init", "--yes"): ("kb_distillery.init_kb", ["--yes"]),
            ("doctor", "--json"): ("kb_distillery.doctor", ["--json"]),
            ("kb", "list"): ("kb_distillery.kbconfig", ["list"]),
            ("kb", "show", "--kb", "x"): ("kb_distillery.kbconfig", ["show", "--kb", "x"]),
            ("ops", "status"): ("kb_distillery.ops", ["status"]),
            ("ship", "status"): ("kb_distillery.git.ship", ["status"]),
            ("ingest", "status"): ("kb_distillery.ingest", ["status"]),
            ("digest", "easy", "p1"): ("kb_distillery.ingest", ["easy-digest", "p1"]),
            ("digest", "full", "p1"): ("kb_distillery.ingest", ["full-digest", "p1"]),
            ("digest", "deep", "p1"): ("kb_distillery.ingest", ["deep-digest", "p1"]),
            ("digest", "many", "submit"): ("kb_distillery.ingest", ["digest-many", "submit"]),
            ("digest", "instructions"): ("kb_distillery.core.digest", []),
            ("send", "note.md", "--to", "a,b"): ("kb_distillery.distill.send", ["note.md", "--to", "a,b"]),
            ("lint",): ("kb_distillery.lint.lint", []),
            ("llm", "status"): ("kb_distillery.llm", ["status"]),
            ("share", "status"): ("kb_distillery.publish.cloudflare", ["status"]),
            ("propose", "review"): ("kb_distillery.graph.propose", ["review"]),
            ("hooks", "install", "--kb", "demo"): ("kb_distillery.git.install_hooks", ["--kb", "demo"]),
            ("hook", "guard"): ("kb_distillery.git.guard", []),
            ("hook", "git-guard"): ("kb_distillery.git.git_guard", []),
            ("hook", "pre-commit"): ("kb_distillery.lint.lint", []),
            ("hook", "commit-msg", ".git/COMMIT_EDITMSG"): ("kb_distillery.git.commit_policy", ["msg", ".git/COMMIT_EDITMSG"]),
            ("hook", "pre-push", "origin", "url"): ("kb_distillery.git.commit_policy", ["push", "origin", "url"]),
        }
        with patch.object(tree, "repo_root", return_value=ROOT):
            for argv, (module, args) in cases.items():
                code, seen = self.run_with_fake(list(argv))
                self.assertEqual(code, 0, argv)
                self.assertEqual(seen["module"], module, argv)
                self.assertEqual(seen["argv"][1:], args, argv)

    def test_every_leaf_is_reachable_from_the_command_line(self):
        for path, cmd in leaves():
            found = tree.resolve(list(path) + ["--x"])
            self.assertIsNotNone(found, path)
            self.assertEqual(found[0], path)
            self.assertEqual(found[2], ["--x"])

    def test_scripts_run_from_the_checkout_and_are_refused_outside_one(self):
        calls = []
        with patch.object(tree.subprocess, "call", side_effect=lambda cmd: calls.append(cmd) or 0), \
                patch.object(tree, "repo_root", return_value=ROOT):
            self.assertEqual(tree.main(["launch", "--port", "9000"]), 0)
        self.assertEqual(calls[0], ["bash", os.path.join(ROOT, "scripts/launch.sh"), "--port", "9000"])

        def refuse(what):
            raise NotInCheckout(f"{what} needs a checkout")

        with patch.object(tree, "require_repo_root", side_effect=refuse):
            code, _, err = call(tree.main, ["ship", "status"])
            self.assertEqual(code, 2)
            self.assertIn("distill ship needs a checkout", err)

    def test_the_hooks_commands_work_outside_a_checkout(self):
        """The hooks ship in the wheel: `hooks install` and every `hook <name>` need no repository."""
        with patch.object(tree, "repo_root", return_value=None):
            for argv, module in ((["hooks", "install", "--kb", "x"], "kb_distillery.git.install_hooks"),
                                 (["hook", "guard"], "kb_distillery.git.guard"), (["hook", "pre-commit"], "kb_distillery.lint.lint")):
                code, seen = self.run_with_fake(argv)
                self.assertEqual((code, seen["module"]), (0, module), argv)
            self.assertNotIn("hooks", [n for n, c in tree.COMMANDS.items() if c.checkout_only])
            self.assertFalse(any(c.checkout_only for c in tree.COMMANDS["hooks"].sub.values()))

    def test_every_hook_fails_closed(self):
        """A hook allows (0) or denies (2): an import error, a crash or any other exit code denies. Claude Code lets a tool
        call through on every code but 2, so exit 1 from a guard would be a hole."""
        for name, cmd in tree.COMMANDS["hook"].sub.items():
            self.assertTrue(cmd.fail_closed, name)
            for raised, want in ((ImportError("No module named 'x'"), 2), (RuntimeError("boom"), 2), (SystemExit(1), 2),
                                 (SystemExit(2), 2), (SystemExit(127), 2), (SystemExit(0), 0), (SystemExit(None), 0)):
                with patch.object(tree.runpy, "run_module", side_effect=raised):
                    code, _, err = call(tree.main, ["hook", name])
                self.assertEqual(code, want, (name, raised))
                if isinstance(raised, (ImportError, RuntimeError)):
                    self.assertIn("fail closed", err)
            with patch.object(tree.runpy, "run_module", return_value=None):
                self.assertEqual(call(tree.main, ["hook", name])[0], 0)

    def test_other_commands_still_pass_exit_codes_and_errors_through(self):
        with patch.object(tree.runpy, "run_module", side_effect=SystemExit(1)):
            self.assertEqual(call(tree.main, ["lint"])[0], 1)
        with patch.object(tree.runpy, "run_module", side_effect=ImportError("x")), self.assertRaises(ImportError):
            tree.main(["lint"])

    def test_a_real_missing_module_denies(self):
        with patch.dict(tree.COMMANDS["hook"].sub, {"guard": tree.Cmd("x", target="kb_distillery.git.no_such_module",
                                                                     config_check=False, fail_closed=True)}):
            code, _, err = call(tree.main, ["hook", "guard"])
        self.assertEqual(code, 2)
        self.assertIn("fail closed", err)

    def test_launch_outside_a_checkout_serves_the_app_in_the_foreground(self):
        with patch.object(tree, "repo_root", return_value=None):
            _, seen = self.run_with_fake(["launch"])
            self.assertEqual((seen["module"], seen["argv"][1:]), ("kb_distillery.api", ["--port", "8765"]))
            _, seen = self.run_with_fake(["launch", "--port", "9000"])
            self.assertEqual(seen["argv"][1:], ["--port", "9000"])

    def test_kb_list_finds_a_kb(self):
        with tempfile.TemporaryDirectory() as bases:
            folder = os.path.join(bases, "kb-probe")
            os.makedirs(folder)
            with open(os.path.join(folder, "kb.toml"), "w") as f:
                f.write('[kb]\nid = "probe"\nname = "Probe"\nschema_version = "1.5"\n')
            cp = run_cli(["kb", "list"], self.home, {"KB_BASES_DIR": bases})
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("probe", cp.stdout)


class KbdAliasTests(TempHome):
    def forward(self, argv):
        seen = []
        with patch.object(tree, "main", side_effect=lambda a: seen.append(list(a)) or 0):
            code, _, err = call(legacy.kbd_main, argv)
        return code, seen, err

    def test_every_old_command_maps_to_a_real_distill_command(self):
        for old, new in legacy.KBD_MAP.items():
            found = tree.resolve(list(new))
            self.assertIsNotNone(found, f"kbd {old} -> distill {' '.join(new)}")

    def test_the_mapping_the_plan_names(self):
        self.assertEqual(legacy.KBD_MAP["distill"], ("send",))
        self.assertEqual(legacy.KBD_MAP["kb-list"], ("kb", "list"))
        self.assertEqual(legacy.KBD_MAP["kb-show"], ("kb", "show"))
        self.assertEqual(legacy.KBD_MAP["app"], ("launch",))
        self.assertEqual(legacy.KBD_MAP["install-kb-hooks"], ("hooks", "install"))
        self.assertEqual(legacy.KBD_MAP["health"], ("lint", "--health"))

    def test_forwards_with_a_one_line_deprecation_on_stderr(self):
        code, seen, err = self.forward(["distill", "note.md", "--to", "a,b"])
        self.assertEqual((code, seen), (0, [["send", "note.md", "--to", "a,b"]]))
        self.assertEqual(err.strip().count("\n"), 0)
        self.assertIn("deprecated", err)
        self.assertIn("distill send", err)

    def test_forwards_the_rest_of_the_line_untouched(self):
        self.assertEqual(self.forward(["kb-list"])[1], [["kb", "list"]])
        self.assertEqual(self.forward(["health", "--kb", "demo"])[1], [["lint", "--health", "--kb", "demo"]])
        self.assertEqual(self.forward(["app", "--port", "9000"])[1], [["launch", "--port", "9000"]])
        self.assertEqual(self.forward(["ops", "status"])[1], [["ops", "status"]])

    def test_exit_code_comes_back(self):
        with patch.object(tree, "main", return_value=7):
            code, _, _ = call(legacy.kbd_main, ["lint"])
        self.assertEqual(code, 7)

    def test_help_lists_every_old_command_and_its_replacement(self):
        for argv in ([], ["--help"], ["-h"], ["help"]):
            code, out, _ = call(legacy.kbd_main, argv)
            self.assertEqual(code, 0)
            for old, new in legacy.KBD_MAP.items():
                self.assertIn(old, out)
                self.assertIn("distill " + " ".join(new), out)

    def test_unknown_old_command_exits_2(self):
        code, _, err = call(legacy.kbd_main, ["nope"])
        self.assertEqual(code, 2)
        self.assertIn("unknown command", err)

    def test_runs_end_to_end(self):
        cp = run_cli(["kb-list"], self.home, {"KB_BASES_DIR": os.path.join(self.home, "none")}, entry="kb_distillery.cli.legacy")
        self.assertIn("deprecated", cp.stderr)
        self.assertIn("distill kb list", cp.stderr)


class EntryPointTests(unittest.TestCase):
    def test_pyproject_points_distill_and_kbd_at_the_cli_package(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
            scripts = tomllib.load(f)["project"]["scripts"]
        self.assertEqual(scripts["distill"], "kb_distillery.cli:main")
        self.assertEqual(scripts["kbd"], "kb_distillery.cli:kbd_main")
        self.assertIs(cli.main, tree.main)
        self.assertIs(cli.kbd_main, legacy.kbd_main)


class ConfigMigrationTests(TempHome):
    """Only the old config folder exists: print the exact mv and exit 1; never move anything."""

    def test_a_command_stops_with_the_exact_mv(self):
        self.legacy_only()
        old, new = os.path.join(self.home, ".config", "thesis-kb"), os.path.join(self.home, ".config", "kb-distillery")
        with patch.object(tree.runpy, "run_module") as run:
            code, _, err = call(tree.main, ["llm", "status"])
        self.assertEqual(code, 1)
        self.assertIn(f"mv {old} {new}", err)
        run.assert_not_called()
        self.assertTrue(os.path.isdir(old), "the old folder is still there")
        self.assertFalse(os.path.exists(new), "nothing was moved for the user")

    def test_end_to_end_in_a_subprocess(self):
        self.legacy_only()
        cp = run_cli(["llm", "status"], self.home)
        self.assertEqual(cp.returncode, 1)
        self.assertIn("mv ", cp.stderr)
        self.assertIn(".config/kb-distillery", cp.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".config", "thesis-kb", "anthropic_key")))

    def test_help_doctor_hooks_and_ship_are_not_blocked(self):
        self.legacy_only()
        self.assertEqual(call(tree.main, ["--help"])[0], 0)
        self.assertEqual(call(tree.main, ["lint", "--help"])[0], 0)
        with patch.object(tree.runpy, "run_module") as run, patch.object(tree, "repo_root", return_value=ROOT):
            for argv in (["doctor"], ["hook", "guard"], ["hook", "pre-push"], ["ship", "status"], ["kb", "list"], ["lint"],
                         ["hooks", "install"]):
                self.assertEqual(tree.main(argv), 0, argv)
            self.assertEqual(run.call_count, 7)

    def test_a_forwarded_help_is_not_blocked_either(self):
        self.legacy_only()
        with patch.object(tree.runpy, "run_module") as run:
            self.assertEqual(tree.main(["ingest", "--help"]), 0)
        run.assert_called_once()

    def test_not_blocked_once_the_new_folder_exists(self):
        self.legacy_only()
        os.makedirs(os.path.join(self.home, ".config", "kb-distillery"))
        with patch.object(tree.runpy, "run_module") as run:
            self.assertEqual(tree.main(["llm", "status"]), 0)
        run.assert_called_once()

    def test_unknown_help_target_exits_2_and_argv_is_restored(self):
        self.assertEqual(call(tree.main, ["help", "nope"])[0], 2)
        before = list(sys.argv)
        with patch.object(tree.runpy, "run_module"):
            tree.main(["lint", "--x"])
        self.assertEqual(sys.argv, before)

    def test_not_blocked_with_no_config_folder_at_all(self):
        with patch.object(tree.runpy, "run_module") as run:
            self.assertEqual(tree.main(["llm", "status"]), 0)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
