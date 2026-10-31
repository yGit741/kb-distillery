"""Distilling one think note into two kbs: pages with a `think:` source, a provenance sidecar, idempotent re-runs."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb.distill import fanout
from tests.conftest import FIXTURE_KB


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def lint(root):
    env = dict(os.environ, KB_ROOT=root, KB="")
    return subprocess.run([sys.executable, "-m", "kb.lint.lint"], env=env, capture_output=True, text=True)


class Fanout(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = os.path.realpath(tmp.name)
        self.think = os.path.join(base, "think")
        self.a, self.b = os.path.join(base, "a"), os.path.join(base, "b")
        for root in (self.a, self.b):
            shutil.copytree(FIXTURE_KB, root)
        write(os.path.join(self.think, "Thesis Decision.md"), "---\ntags: x\n---\n\nWe pick tensors.\nSecond line.\n\nMore.\n")
        write(os.path.join(self.think, "lab", "idea.md"), "A nested note about margins.\n")
        self.kbs = [("a", self.a), ("b", self.b)]

    def run_note(self, note="Thesis Decision", **k):
        return fanout.distill_note(note, self.kbs, think_root=self.think, **k)

    def test_two_kbs_get_a_page_citing_the_note_and_the_note_records_both(self):
        out = self.run_note(now="2026-10-31T10:00:00Z")
        self.assertEqual([(o.kb, o.written) for o in out], [("a", True), ("b", True)])
        for root in (self.a, self.b):
            page = open(os.path.join(root, "wiki", "distilled-think-thesis-decision.md"), encoding="utf-8").read()
            self.assertIn("source: think:Thesis Decision.md", page)
            self.assertIn("We pick tensors. Second line.", page)
            r = lint(root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        prov = fanout.read_provenance(os.path.realpath(self.think), "Thesis Decision.md")
        self.assertEqual([(e["kb"], e["page"]) for e in prov["distilled"]],
                         [("a", "wiki/distilled-think-thesis-decision.md"), ("b", "wiki/distilled-think-thesis-decision.md")])

    def test_the_note_itself_is_not_touched(self):
        path = os.path.join(self.think, "Thesis Decision.md")
        before = open(path, "rb").read()
        self.run_note()
        self.assertEqual(open(path, "rb").read(), before)

    def test_running_twice_changes_nothing(self):
        self.run_note(now="2026-10-31T10:00:00Z")
        prov_file = fanout.provenance_path(os.path.realpath(self.think), "Thesis Decision.md")
        snap = {p: open(p, "rb").read() for p in (prov_file, os.path.join(self.a, "wiki", "distilled-think-thesis-decision.md"))}
        out = self.run_note(now="2027-01-01T00:00:00Z")
        self.assertEqual([o.written for o in out], [False, False])
        for p, data in snap.items():
            self.assertEqual(open(p, "rb").read(), data)

    def test_a_later_run_adds_only_the_new_kb(self):
        fanout.distill_note("Thesis Decision", [("a", self.a)], think_root=self.think)
        self.run_note()
        prov = fanout.read_provenance(os.path.realpath(self.think), "Thesis Decision.md")
        self.assertEqual([e["kb"] for e in prov["distilled"]], ["a", "b"])

    def test_nested_note_and_spellings(self):
        for spelling in ("lab/idea", "lab/idea.md", "think:lab/idea.md", "think/lab/idea.md"):
            self.assertEqual(fanout.note_rel(spelling, self.think), "lab/idea.md")
        out = fanout.distill_note("lab/idea", [("a", self.a)], think_root=self.think)
        self.assertEqual(out[0].page, "wiki/distilled-think-lab-idea.md")
        self.assertTrue(os.path.isfile(os.path.join(self.think, ".provenance", "lab", "idea.md.json")))

    def test_bad_input_writes_nothing(self):
        for note, kbs in (("missing", self.kbs), ("../x", self.kbs), ("Thesis Decision", self.kbs + [("c", "/nonexistent")])):
            with self.assertRaises(fanout.DistillError):
                fanout.distill_note(note, kbs, think_root=self.think)
        with self.assertRaises(fanout.DistillError):
            fanout.distill_note("Thesis Decision", ["no-such-kb-id"], think_root=self.think)
        self.assertFalse(os.path.exists(os.path.join(self.think, ".provenance")))
        self.assertFalse(os.path.exists(os.path.join(self.a, "wiki", "distilled-think-thesis-decision.md")))

    def test_a_page_of_another_note_is_a_collision_and_blocks_the_whole_run(self):
        write(os.path.join(self.think, "thesis decision.md"), "Other.\n")      # same slug, different note
        fanout.distill_note("thesis decision", [("b", self.b)], think_root=self.think)
        with self.assertRaises(fanout.DistillError):
            self.run_note()
        self.assertFalse(os.path.exists(os.path.join(self.a, "wiki", "distilled-think-thesis-decision.md")))

    def test_the_skill_and_the_command_name_the_page_alike(self):
        from kb.distill import paths
        for name in ("0. Mathematical Prerequisite", "1.  my-true-research-start-here", "Points to Meeting with GIl", "lab/idea"):
            self.assertEqual(paths.distilled_slug(f"think/{name}.md"), fanout.slug_for(f"{name}.md"))

    def test_think_citations_resolve_in_both_spellings(self):
        self.assertTrue(fanout.resolve_cite("think:Thesis Decision.md", self.think).endswith("Thesis Decision.md"))
        self.assertTrue(fanout.resolve_cite("think/lab/idea.md", self.think).endswith("idea.md"))
        self.assertIsNone(fanout.resolve_cite("think:gone.md", self.think))
        self.assertIsNone(fanout.resolve_cite("think:../x.md", self.think))
        self.assertIsNone(fanout.resolve_cite("raw/x.md", self.think))

    def test_summarizer_is_called_once_for_all_kbs(self):
        calls = []
        self.run_note(summarize=lambda body, title: calls.append((body, title)) or "Fake summary.")
        self.assertEqual(len(calls), 1)
        self.assertIn("Fake summary.", open(os.path.join(self.b, "wiki", "distilled-think-thesis-decision.md")).read())

    def test_llm_summarizer_goes_through_kb_llm_with_the_chosen_backend(self):
        from kb import llm
        seen = {}

        def fake_ask(prompt, backend=None, **kw):
            seen.setdefault("prompts", []).append(prompt)
            seen["backend"] = backend
            return llm.Result(id="r0", text=" Short. ", backend=backend or "subscription")

        with patch.object(llm, "ask", fake_ask):
            self.assertEqual(fanout.llm_summarizer("api")("body text", "T"), "Short.")
            fanout.llm_summarizer()("x", "T")
        self.assertIn("body text", seen["prompts"][0])
        self.assertIsNone(seen["backend"])          # None -> kb.llm resolves $KB_LLM_BACKEND, then subscription

    def test_llm_failure_aborts_before_any_write(self):
        from kb import llm
        with patch.object(llm, "ask", lambda *a, **k: llm.Result(id="r0", error="boom")):
            with self.assertRaises(fanout.DistillError):
                self.run_note(summarize=fanout.llm_summarizer("batch"))
        self.assertFalse(os.path.exists(os.path.join(self.think, ".provenance")))


if __name__ == "__main__":
    unittest.main()
