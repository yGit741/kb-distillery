"""kbd: the command table, the dispatcher, and that --help needs no knowledge base."""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery import cli
from kb_distillery import kbconfig

SRC = os.path.join(kbconfig.checkout_root(), "src")


def _run(args, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k not in ("KB", "KB_ROOT", "KB_BASES_DIR")}
    env["PYTHONPATH"] = SRC
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-m", "kb_distillery.cli", *args], capture_output=True, text=True, env=env, check=False)


class CommandTableTests(unittest.TestCase):
    def test_every_target_exists(self):
        for name, (kind, target, _fixed, _help) in cli.COMMANDS.items():
            if kind == "module":
                self.assertIsNotNone(importlib.util.find_spec(target), f"{name}: no module {target}")
            else:
                self.assertTrue(os.path.isfile(os.path.join(kbconfig.checkout_root(), target)), f"{name}: no script {target}")

    def test_help_lists_every_command(self):
        for argv in ([], ["--help"], ["-h"], ["help"]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(argv), 0)
            for name in cli.COMMANDS:
                self.assertIn(name, out.getvalue())

    def test_unknown_command_exits_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["nope"]), 2)
        self.assertIn("unknown command", err.getvalue())


class DispatchTests(unittest.TestCase):
    def test_hands_the_rest_of_the_line_to_the_module_and_returns_its_exit_code(self):
        seen = {}

        def fake(module, run_name, alter_sys):
            seen.update(module=module, argv=list(sys.argv))
            raise SystemExit(3)

        with patch("kb_distillery.cli.runpy.run_module", side_effect=fake), patch.object(sys, "argv", ["kbd"]):
            self.assertEqual(cli.main(["health", "--kb", "demo"]), 3)
        self.assertEqual(seen["module"], "kb_distillery.lint.lint")
        self.assertEqual(seen["argv"], ["kbd health", "--health", "--kb", "demo"])

    def test_app_defaults_the_port_unless_given(self):
        argvs = []

        def fake(module, run_name, alter_sys):
            argvs.append(list(sys.argv))

        with patch("kb_distillery.cli.runpy.run_module", side_effect=fake), patch.object(sys, "argv", ["kbd"]):
            cli.main(["app"])
            cli.main(["app", "--port", "9000"])
        self.assertEqual(argvs[0][1:], ["--port", "8765"])
        self.assertEqual(argvs[1][1:], ["--port", "9000"])


class EndToEndTests(unittest.TestCase):
    def test_importing_cli_does_not_load_kbconfig(self):
        cp = subprocess.run([sys.executable, "-c", "import sys, kb_distillery.cli; print('kb_distillery.kbconfig' in sys.modules)"],
                            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": SRC}, check=False)
        self.assertEqual(cp.stdout.strip(), "False", cp.stderr)

    def test_help_works_with_no_knowledge_base(self):
        cp = _run(["--help"], {"KB_BASES_DIR": os.path.join(tempfile.gettempdir(), "kbd-no-such-dir")})
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("kb-list", cp.stdout)

    def test_kb_list_finds_a_kb(self):
        with tempfile.TemporaryDirectory() as bases:
            folder = os.path.join(bases, "kb-probe")
            os.makedirs(folder)
            with open(os.path.join(folder, "kb.toml"), "w") as f:
                f.write('[kb]\nid = "probe"\nname = "Probe"\nschema_version = "1.4"\n')
            cp = _run(["kb-list"], {"KB_BASES_DIR": bases})
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn("probe", cp.stdout)


if __name__ == "__main__":
    unittest.main()
