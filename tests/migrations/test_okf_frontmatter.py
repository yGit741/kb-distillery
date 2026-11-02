"""0013_okf_frontmatter: status -> maturity (+ OKF draft), summary -> description, summary_by -> generated, date -> created,
title dropped when it is the H1, sources as objects (never only the url), generated.by only, related as page paths, excalidraw type; idempotent, body untouched."""
import importlib.util
import json
import os
import tempfile
import unittest

from kb_distillery.core import frontmatter, links
from kb_distillery.paths import MIGRATIONS_CODE_PATH

spec = importlib.util.spec_from_file_location("m0013", os.path.join(MIGRATIONS_CODE_PATH, "0013_okf_frontmatter.py"))
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)

SUMMARY = "A summary that is long enough to be a real description of the page and its main point, ok."


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


class OkfFrontmatter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(self.root, "kb.toml", '[kb]\nid = "t"\nname = "T"\nschema_version = "1.4"\nowner = "ada"\n')
        write(self.root, "meta/aliases.tsv", "# mention\tslug\nSGD\tsgd\n")
        write(self.root, "wiki/paper-a.md",
              "---\ntype: paper\nlayer: source\nstatus: to-read\ndepth: listed\nurl: https://example.org/a\n"
              "related: [idea-x, old-name, sgd, nowhere]\nsources: [idea-x, think:note one.md]\n---\n\n# Paper A\n\nBody [[idea-x]].\n")
        write(self.root, "wiki/idea-x.md",
              f'---\ntype: idea\nlayer: concept\nstatus: seed\ndate: 2026-10-15\nsummary: "{SUMMARY}"\n'
              f"summary_from: abc\nsummary_by: me\naliases: [old-name]\nrelated:\n  - sgd\n---\n\n# Idea X\n")
        write(self.root, "wiki/sgd.md",
              f'---\ntype: idea\nlayer: concept\nstatus: growing\nsummary: "{SUMMARY}"\nsummary_from: h1\n---\n\n# SGD\n')
        write(self.root, "wiki/excalidraw/d.excalidraw.md", "---\nexcalidraw-plugin: parsed\n---\n\nbody\n")
        write(self.root, ".cache/summaries/proposals.jsonl",
              json.dumps({"slug": "sgd", "summary": SUMMARY, "summary_from": "h1", "model": "sonnet",
                          "ts": "2026-10-31T09:46:51"}) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pages(self):
        rep = mig.apply(self.root)
        paper = frontmatter.parse(read(self.root, "wiki/paper-a.md"))[0]
        self.assertEqual(paper["maturity"], "to-read")
        self.assertEqual(paper["status"], "draft")
        self.assertNotIn("title", paper)                             # equals the H1: readers fall back to it
        self.assertEqual(frontmatter.resources(paper),
                         ["https://example.org/a", links.page_path("idea-x"), "think:note one.md"])
        self.assertEqual(paper["related"], ["idea-x.md", "sgd.md", "nowhere.md"])
        self.assertEqual(rep["related_unresolved"], [("paper-a", "nowhere")])
        idea = frontmatter.parse(read(self.root, "wiki/idea-x.md"))[0]
        self.assertNotIn("status", idea)
        self.assertEqual(idea["created"], "2026-10-15T00:00:00Z")
        self.assertEqual(idea["generated"], {"by": "human:ada"})
        self.assertEqual(idea["related"], ["sgd.md"])
        self.assertIn("description", idea)
        sgd = frontmatter.parse(read(self.root, "wiki/sgd.md"))[0]
        self.assertEqual(sgd["generated"], {"by": "summarize/sonnet"})      # no `at`
        self.assertTrue(read(self.root, "wiki/excalidraw/d.excalidraw.md").startswith("---\ntype: excalidraw\n"))

    def test_body_untouched_and_idempotent(self):
        before = read(self.root, "wiki/paper-a.md").split("\n---\n", 1)[1]
        mig.apply(self.root)
        after = {r: read(self.root, r) for r in ("wiki/paper-a.md", "wiki/idea-x.md", "wiki/sgd.md")}
        self.assertEqual(after["wiki/paper-a.md"].split("\n---\n", 1)[1], before)
        again = mig.apply(self.root)
        self.assertEqual(again["changed"], [])
        self.assertEqual({r: read(self.root, r) for r in after}, after)

    def test_distilled_think_source_moves_into_sources_and_raw_is_dropped(self):
        write(self.root, "wiki/distilled-think-n.md",
              "---\ntype: distilled-think\nlayer: concept\nstatus: review\nsource: think:n.md\n---\n\n# Distilled\n")
        write(self.root, "wiki/paper-r.md", "---\ntype: paper\nlayer: source\nstatus: digested\nsources: [raw/x.pdf]\n---\n\n# R\n")
        rep = mig.apply(self.root)
        d = frontmatter.parse(read(self.root, "wiki/distilled-think-n.md"))[0]
        self.assertEqual(frontmatter.resources(d), ["think:n.md"])
        self.assertNotIn("source", d)
        self.assertEqual(rep["source_dropped"], [("paper-r", "raw/x.pdf")])

    def test_sources_that_only_repeat_the_url_and_titles_equal_to_the_heading_are_omitted(self):
        write(self.root, "wiki/paper-u.md", "---\ntype: paper\nlayer: source\nurl: https://example.org/u\n"
              "title: \"Paper U\"\nsources: [https://example.org/u]\n---\n\n# Paper U\n")
        write(self.root, "wiki/paper-o.md", "---\ntype: paper\nlayer: source\nurl: https://example.org/o\n"
              "title: \"Other name\"\nsources: [{resource: https://example.org/o}]\n---\n\n# Paper O\n")
        write(self.root, "wiki/paper-m.md", "---\ntype: paper\nlayer: source\nurl: https://example.org/m\n"
              "sources: [idea-x]\n---\n\n# Paper M\n")
        rep = mig.apply(self.root)
        u, o, m = (frontmatter.parse(read(self.root, f"wiki/paper-{x}.md"))[0] for x in "uom")
        self.assertNotIn("sources", u)
        self.assertNotIn("title", u)
        self.assertEqual(frontmatter.resources(u), ["https://example.org/u"])      # the url stands in
        self.assertNotIn("sources", o)                                              # an object form is dropped too
        self.assertEqual(o["title"], '"Other name"')                                # differs from the H1: kept
        self.assertEqual([t[0] for t in rep["title_differs"]], ["paper-o"])
        self.assertEqual(frontmatter.resources(m), ["https://example.org/m", "idea-x.md"])   # other entries: kept, url inside

    def test_dry_run_writes_nothing(self):
        text = read(self.root, "wiki/sgd.md")
        mig.apply(self.root, dry_run=True)
        self.assertEqual(read(self.root, "wiki/sgd.md"), text)

    def test_owner_key_is_required_for_a_hand_written_summary(self):
        write(self.root, "kb.toml", '[kb]\nid = "t"\nname = "T"\nschema_version = "1.4"\n')
        with self.assertRaisesRegex(RuntimeError, r"\[kb\] owner"):
            mig.apply(self.root)

    def test_page_path_is_the_only_builder(self):
        self.assertEqual(links.page_path("a-b"), "a-b.md")
        self.assertEqual(links.page_slug("a-b.md"), "a-b")
        self.assertIsNone(links.page_slug("think:x.md"))
        self.assertIsNone(links.page_slug("https://x.org/a.md"))

    def _bytes(self, rel):
        with open(os.path.join(self.root, rel), "rb") as f:
            return f.read().decode()

    def test_crlf_pages_are_migrated_and_stay_crlf(self):
        with open(os.path.join(self.root, "wiki/crlf.md"), "wb") as f:
            f.write(b"---\r\ntype: idea\r\nlayer: concept\r\nstatus: seed\r\n---\r\n\r\n# Crlf\r\n\r\nBody.\r\n")
        with open(os.path.join(self.root, "wiki/excalidraw/e.excalidraw.md"), "wb") as f:
            f.write(b"---\r\nexcalidraw-plugin: parsed\r\n---\r\n\r\nbody\r\n")
        rep = mig.apply(self.root)
        text = self._bytes("wiki/crlf.md")
        self.assertIn("maturity: seed\r\n", text)
        self.assertNotIn("title", text)
        self.assertTrue(text.endswith("---\r\n\r\n# Crlf\r\n\r\nBody.\r\n"))
        self.assertNotIn("\n", text.replace("\r\n", ""))                    # no bare LF anywhere
        self.assertIn("type: excalidraw\r\n", self._bytes("wiki/excalidraw/e.excalidraw.md"))
        self.assertIn("wiki/crlf.md", rep["changed"])

    def test_a_frontmatter_mixing_line_ends_stops_loudly_before_any_write(self):
        with open(os.path.join(self.root, "wiki/mixed.md"), "wb") as f:
            f.write(b"---\r\ntype: idea\nlayer: concept\r\nstatus: seed\r\n---\r\n\r\n# M\r\n")
        before = self._bytes("wiki/paper-a.md")
        with self.assertRaises(RuntimeError) as cm:
            mig.apply(self.root)
        self.assertIn("wiki/mixed.md", str(cm.exception))
        self.assertEqual(self._bytes("wiki/paper-a.md"), before)


if __name__ == "__main__":
    unittest.main()
