"""`kbd distill <note> --to a,b` end to end on a temp think folder and two temp kb repos (never the real think)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from kb import cli
from kb.distill import fanout, send
from tests.conftest import FIXTURE_KB

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "KB_NO_PUSH": "1", "KB_SHARE_AUTODEPLOY": "0"}


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout


class Send(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = os.path.realpath(tmp.name)
        for name in ("a", "b"):
            root = os.path.join(self.base, name)
            shutil.copytree(FIXTURE_KB, root)
            toml = os.path.join(root, "kb.toml")
            with open(toml) as f:
                text = f.read()
            with open(toml, "w") as f:
                f.write(text.replace('id = "fixture"', f'id = "{name}"'))
            g(root, "init", "-q", "-b", "main")
            g(root, "config", "user.name", "t")
            g(root, "config", "user.email", "t@t")
            g(root, "add", "-A")
            g(root, "commit", "-q", "-m", "init")
        os.makedirs(os.path.join(self.base, "think"))
        with open(os.path.join(self.base, "think", "decision.md"), "w") as f:
            f.write("We pick tensors.\n\nMore.\n")
        p = patch.dict(os.environ, dict(ENV, KB_BASES_DIR=self.base))
        p.start()
        self.addCleanup(p.stop)
        lint = patch("kb.ops.core.run_lint")           # the fixture kb has its own lint tests; here the commit is the subject
        lint.start()
        self.addCleanup(lint.stop)

    def go(self, *extra, **k):
        return send.main(["decision", "--to", "a,b", *extra], **k)

    def test_two_kbs_each_get_a_kb_distill_commit_and_the_note_records_both(self):
        self.assertEqual(self.go(), 0)
        for name in ("a", "b"):
            root = os.path.join(self.base, name)
            self.assertTrue(g(root, "log", "-1", "--format=%s").startswith("kb(distill):"))
            self.assertEqual(g(root, "status", "--porcelain", "-uno").strip(), "")
        prov = fanout.read_provenance(os.path.join(self.base, "think"), "decision.md")
        self.assertEqual([e["kb"] for e in prov["distilled"]], ["a", "b"])

    def test_second_run_adds_no_commit(self):
        self.go()
        heads = [g(os.path.join(self.base, n), "rev-parse", "HEAD") for n in "ab"]
        self.assertEqual(self.go(), 0)
        self.assertEqual(heads, [g(os.path.join(self.base, n), "rev-parse", "HEAD") for n in "ab"])

    def test_no_commit_leaves_the_pages_uncommitted(self):
        self.assertEqual(self.go("--no-commit"), 0)
        root = os.path.join(self.base, "a")
        self.assertIn("distilled-think-decision.md", g(root, "status", "--porcelain"))

    def test_unknown_kb_or_note_fails_without_writing(self):
        self.assertEqual(send.main(["decision", "--to", "a,nope"]), 1)
        self.assertEqual(send.main(["missing", "--to", "a"]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.base, "think", ".provenance")))

    def test_summarize_uses_the_chosen_backend_through_kb_llm(self):
        from kb import llm
        seen = []

        def fake(prompt, backend=None, **kw):
            seen.append(backend)
            return llm.Result(id="r0", text="LLM summary.", backend=backend or "subscription")

        with patch.object(llm, "ask", fake):
            self.assertEqual(self.go("--summarize", "--backend", "batch", "--no-commit"), 0)
        self.assertEqual(seen, ["batch"])           # once for two kbs
        self.assertIn("LLM summary.", open(os.path.join(self.base, "b", "wiki", "distilled-think-decision.md")).read())

    def test_backend_without_summarize_is_refused(self):
        self.assertEqual(self.go("--backend", "api"), 2)

    def test_kbd_front_door_routes_distill(self):
        self.assertIn("distill", cli.COMMANDS)
        self.assertEqual(cli.COMMANDS["distill"][1], "kb.distill.send")


if __name__ == "__main__":
    unittest.main()
