"""migrate_model on a small synthetic vault: raw by format, collections, slugs, links, hubs."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from kb.maintenance import migrate_model as mm
from kb.lint.lint import parse_frontmatter

CONFIG = ("key\thub\ttype\ttitle\tshort\tinstitution\tcourse_code\tsemester\tlecturer\tmerge\n"
          "rl\tcourse-runi-rl\tcourse\tReinforcement Learning\trl\truni\t1234\t2024a\t-\tmoc-rl,source-rl\n")
PAGES = {
    "2020-x": "---\ntype: paper\nstatus: digested\nraw: raw/papers/nadav-cohen/2020-x.pdf\n---\n\n"
              "# X\n\n**Problem:** how does gradient descent pick a solution\n",
    "moc-rl": "---\ntype: moc\nstatus: growing\narea: [rl]\n---\n\n# RL\n\nLearning from reward.\n\n"
              "## Scope\n\nMDPs.\n\n## Raw material\n\n- `raw/slides/rl/`\n\n## Threads\n\n- [[2020-x]]\n",
    "source-rl": "---\ntype: source\nformat: course\nraw: raw/slides/rl/\nstatus: digested\n---\n\n# RL\n",
    "moc-quantum": "---\ntype: moc\nstatus: seed\n---\n\n# Quantum\n\n## Papers\n\n- [[2020-x]]\n",
    "source-chat-stub": "---\ntype: source\nformat: chat\nstatus: to-read\nraw: raw/chats/stub.md\n---\n\n# stub\n",
    "source-gemini-muon": "---\ntype: source\nformat: chat\nraw: raw/chats/muon.md\nstatus: digested\n"
                          "---\n\n# Muon\n\n" + "word " * 120 + "\n",
    "tensor-rank": "---\ntype: concept\nstatus: seed\nrelated: [2020-x, moc-rl]\n---\n\n# Tensor rank\n\n"
                   "See [[2020-x|the paper]], [[moc-rl]], [[source-chat-stub]] and `raw/papers/nadav-cohen/2020-x.pdf`.\n",
    "nadav-cohen": "---\ntype: person\nstatus: seed\n---\n\n# Nadav Cohen\n",
}
RAW = ["raw/papers/nadav-cohen/2020-x.pdf", "raw/papers/gal-vardi/2020-x.pdf",
       "raw/slides/rl/Lecture 1 - Intro.pdf", "raw/notes/rl/Recap - Bellman.pdf",
       "raw/chats/stub.md", "raw/chats/muon.md", "raw/mail/2021-01-02-re/thread.md"]


class MigrateTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for rel in RAW:
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)), exist_ok=True)
            with open(os.path.join(self.root, rel), "w") as f:
                f.write("same bytes" if "2020-x" in rel else rel)
        os.makedirs(os.path.join(self.root, "wiki"))
        os.makedirs(os.path.join(self.root, "meta"))
        for slug, text in dict(PAGES, **{"gal-vardi": PAGES["nadav-cohen"]}).items():
            with open(os.path.join(self.root, "wiki", f"{slug}.md"), "w") as f:
                f.write(text)
        rows = ["path\tsha1\tkind\tdisposition\tslug"]
        for rel in RAW:
            sha = "dup" if "2020-x" in rel else rel[-8:]
            rows.append(f"{rel}\t{sha}\t{rel.split('/')[1]}\tskip\t")
        with open(os.path.join(self.root, "meta", "corpus.tsv"), "w") as f:
            f.write("\n".join(rows) + "\n")
        self.cfg = os.path.join(self.root, "collections.tsv")
        with open(self.cfg, "w") as f:
            f.write(CONFIG)
        # notes PDFs with no text layer are handwritten; the fixture's fake PDFs have none
        patcher = mock.patch.object(mm, "has_text_layer", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.root)

    def migrate(self):
        plan, pages, out, rows = mm.build(self.root, self.cfg)
        mm.apply(self.root, plan, pages, out, rows, rewrite_think=False)
        return plan, rows

    def page(self, slug):
        with open(os.path.join(self.root, "wiki", f"{slug}.md")) as f:
            text = f.read()
        return parse_frontmatter(text), text

    def test_raw_by_format_and_collection(self):
        plan, rows = self.migrate()
        self.assertTrue(os.path.isfile(os.path.join(self.root, "raw/printed-docs/2020-x.pdf")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "raw/presentations/rl-lecture-1-intro.pdf")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "raw/handwritten/rl-recap-bellman.pdf")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "raw/emails/2021-01-02-re/thread.md")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "raw/papers")))
        # co-authored duplicate collapsed, both people kept
        self.assertEqual(sorted(rows["raw/printed-docs/2020-x.pdf"]["collection"].split(",")),
                         ["gal-vardi", "nadav-cohen"])
        self.assertEqual(rows["raw/presentations/rl-lecture-1-intro.pdf"]["collection"], "course-runi-rl")
        # a course member is backlog now, not a silent skip
        self.assertEqual(rows["raw/presentations/rl-lecture-1-intro.pdf"]["disposition"], "queued")

    def test_slugs_aliases_and_links(self):
        self.migrate()
        fm, text = self.page("paper-2020-x")
        self.assertEqual(fm["raw"], "raw/printed-docs/2020-x.pdf")
        self.assertEqual(fm["aliases"], ["2020-x"])
        self.assertEqual(fm["digestion-status"], "easy")          # Problem filled → easy
        _fm, concept = self.page("tensor-rank")
        self.assertIn("[[paper-2020-x|the paper]]", concept)
        self.assertIn("[[course-runi-rl]]", concept)
        self.assertNotIn("[[source-chat-stub]]", concept)          # quarantined → plain text
        self.assertIn("`raw/printed-docs/2020-x.pdf`", concept)
        self.assertEqual(_fm["related"], ["paper-2020-x", "course-runi-rl"])
        self.assertEqual(self.page("theme-quantum")[0]["type"], "theme")
        fm, _t = self.page("conversation-muon")
        self.assertEqual((fm["type"], fm["model"], fm["aliases"]),
                         ("conversation", "gemini", ["source-gemini-muon"]))
        self.assertFalse(os.path.exists(os.path.join(self.root, "wiki", "source-chat-stub.md")))

    def test_course_hub(self):
        self.migrate()
        fm, text = self.page("course-runi-rl")
        self.assertEqual((fm["type"], fm["institution"], fm["course_code"], fm["short"]),
                         ("course", "runi", "1234", "rl"))
        self.assertEqual(sorted(fm["aliases"]), ["moc-rl", "source-rl"])
        self.assertIn("Learning from reward.", text)
        self.assertIn("`raw/presentations/rl-lecture-1-intro.pdf`", text)
        self.assertIn("`raw/handwritten/rl-recap-bellman.pdf`", text)
        self.assertNotIn("## Raw material", text)
        self.assertIn("## Threads", text)
        quarantined = os.listdir(os.path.join(self.root, "_quarantine"))
        self.assertEqual(len(quarantined), 1)

    def test_idempotent(self):
        self.migrate()
        plan, pages, out, rows = mm.build(self.root, self.cfg)
        self.assertEqual(plan.raw, {})
        self.assertEqual(plan.slug, {})


if __name__ == "__main__":
    unittest.main()
