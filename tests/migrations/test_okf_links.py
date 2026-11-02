"""0014_okf_links: [[wikilinks]] -> [Title](slug.md) in every wiki page, shown text kept, My notes byte for byte."""
import importlib.util
import os
import tempfile
import unittest

from kb_distillery.vault import links
from kb_distillery.paths import MIGRATIONS_CODE_PATH

spec = importlib.util.spec_from_file_location("m0014", os.path.join(MIGRATIONS_CODE_PATH, "0014_okf_links.py"))
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)

FM = "---\ntype: idea\nlayer: concept\n---\n\n"
NOTES = "## My notes\n\nMine: [[alpha]] and [[nope]] and `[[alpha]]`.\n\n### Sub\n[[beta|B]]\n"


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8", newline="") as f:
        return f.read()


class OkfLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(self.root, "kb.toml", '[kb]\nid = "t"\nname = "T"\nschema_version = "1.5"\n')
        write(self.root, "meta/aliases.tsv", "# mention\tslug\nSGD\tbeta\n")
        write(self.root, "wiki/alpha.md", FM + "# Alpha [one] | two\n\nBody.\n")
        write(self.root, "wiki/beta.md", FM.replace("---\n\n", "aliases: [old-beta]\n---\n\n") + "# Beta\n\n## Why it works\n\nText.\n")
        write(self.root, "wiki/plain.md", FM + "Slug-only page, no heading.\n")
        self.page = (
            FM + "# Home\n\n"
            "bare [[alpha]], label [[beta|the Beta]], anchor [[beta#Why it works]], labelled anchor [[beta#Why it works|why]],\n"
            "alias [[old-beta]], mention [[SGD]], no title [[plain]], spaced [[ alpha ]].\n\n"
            "| a | b |\n|---|---|\n| [[alpha]] | [[beta\\|B cell]] |\n\n"
            "`[[alpha]]` and $[[1,2],[3,4]]$ and <!-- [[alpha]] -->\n\n"
            "```\n[[alpha]]\n```\n\n"
            "dead [[nowhere]] and empty [[]] and an embed ![[pic.png]]\n\n" + NOTES)
        write(self.root, "wiki/home.md", self.page)
        write(self.root, "wiki/excalidraw/d.excalidraw.md", "---\ntype: excalidraw\n---\n[[alpha]]\n")
        write(self.root, "raw/img/pic.png", "x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_forms_and_shown_text(self):
        rep = mig.apply(self.root)
        got = read(self.root, "wiki/home.md")
        self.assertIn("bare [Alpha one two](alpha.md),", got)            # the title the app shows: [ ] | become spaces
        self.assertIn("label [the Beta](beta.md),", got)
        self.assertIn("anchor [Beta](beta.md#why-it-works),", got)
        self.assertIn("labelled anchor [why](beta.md#why-it-works),", got)
        self.assertIn("alias [old-beta](beta.md),", got)                 # an alias has no title of its own: the name as written
        self.assertIn("mention [SGD](beta.md),", got)
        self.assertIn("no title [plain](plain.md),", got)                # slug with spaces: `plain`
        self.assertIn("spaced [Alpha one two](alpha.md).", got)
        self.assertIn("| [Alpha one two](alpha.md) | [B cell](beta.md) |", got)   # table cells hold no pipe
        self.assertEqual(rep["via_alias"], 2)

    def test_not_touched(self):
        mig.apply(self.root)
        got = read(self.root, "wiki/home.md")
        self.assertIn("`[[alpha]]` and $[[1,2],[3,4]]$ and <!-- [[alpha]] -->", got)
        self.assertIn("```\n[[alpha]]\n```", got)
        self.assertEqual(read(self.root, "wiki/excalidraw/d.excalidraw.md"), "---\ntype: excalidraw\n---\n[[alpha]]\n")
        self.assertTrue(got.startswith(self.page[:len(FM)]))             # front matter byte for byte

    def test_my_notes_are_byte_identical_and_counted(self):
        rep = mig.apply(self.root)
        got = read(self.root, "wiki/home.md")
        self.assertTrue(got.endswith(NOTES))
        self.assertEqual(rep["notes_wikilinks"], 4)             # every [[..]] in the section, code spans included

    def test_every_my_notes_section_is_kept(self):
        write(self.root, "wiki/twice.md", FM + "# T\n\n## My notes\nfirst [[alpha]]\n\n## Other\n[[alpha]]\n\n## My notes\nsecond [[alpha]]\n")
        mig.apply(self.root)
        self.assertEqual(read(self.root, "wiki/twice.md"),
                         FM + "# T\n\n## My notes\nfirst [[alpha]]\n\n## Other\n[Alpha one two](alpha.md)\n\n## My notes\nsecond [[alpha]]\n")

    def test_unresolved_left_listed_never_guessed(self):
        rep = mig.apply(self.root)
        got = read(self.root, "wiki/home.md")
        self.assertIn("dead [[nowhere]] and empty [[]] and", got)
        self.assertEqual(rep["unresolved"], ["[[nowhere]]"])
        self.assertEqual(rep["embed_unresolved"], [])
        self.assertEqual(rep["before_unresolved"], 1)
        self.assertEqual(rep["after_broken"], [])
        self.assertEqual([w for _s, w in rep["after_wikilinks"]], ["[[nowhere]]"])

    def test_embed_of_a_raw_file(self):
        mig.apply(self.root)
        self.assertIn("![pic.png](../raw/img/pic.png)", read(self.root, "wiki/home.md"))

    def test_unknown_embed_and_missing_anchor_stay(self):
        write(self.root, "wiki/e.md", FM + "![[ghost.png]] [[beta#No such heading]]\n")
        rep = mig.apply(self.root)
        self.assertEqual(read(self.root, "wiki/e.md"), FM + "![[ghost.png]] [[beta#No such heading]]\n")
        self.assertEqual(rep["embed_unresolved"], ["![[ghost.png]]"])
        self.assertEqual(rep["anchor_unresolved"], ["[[beta#No such heading]]"])

    def test_idempotent_and_dry_run(self):
        before = read(self.root, "wiki/home.md")
        rep = mig.apply(self.root, dry_run=True)
        self.assertGreater(rep["converted"], 0)
        self.assertEqual(read(self.root, "wiki/home.md"), before)       # a dry run writes nothing
        mig.apply(self.root)
        once = read(self.root, "wiki/home.md")
        again = mig.apply(self.root)
        self.assertEqual(read(self.root, "wiki/home.md"), once)
        self.assertEqual(again["changed"], [])
        self.assertEqual(again["converted"], 0)

    def test_every_result_resolves_through_the_resolver(self):
        mig.apply(self.root)
        slugs = {"alpha", "beta", "plain", "home"}
        for m in links.PAGE_LINK.finditer(read(self.root, "wiki/home.md")):
            self.assertIn(links.link_parts(m)[1], slugs)
            self.assertEqual(m.group(2) + links.PAGE_SUFFIX, links.page_path(m.group(2)))

    def test_nothing_is_written_when_my_notes_would_change(self):
        orig = links.convert
        try:
            links.convert = lambda body, rs, report=None: body.replace("Mine:", "Theirs:")
            with self.assertRaises(RuntimeError):
                mig.apply(self.root)
        finally:
            links.convert = orig
        self.assertEqual(read(self.root, "wiki/home.md"), self.page)

    def test_report_counts_bytes_of_each_form(self):
        rep = mig.apply(self.root, dry_run=True)
        self.assertGreater(rep["bytes_new"], rep["bytes_wikilink"])
        self.assertGreater(rep["bytes_slug_form"], rep["bytes_wikilink"])

    def test_crlf_page_keeps_its_line_endings(self):
        write(self.root, "wiki/crlf.md", FM + "# C\r\n\r\nsee [[alpha]]\r\n")
        mig.apply(self.root)
        self.assertEqual(read(self.root, "wiki/crlf.md"), FM + "# C\r\n\r\nsee [Alpha one two](alpha.md)\r\n")

    def test_a_fully_crlf_page_with_a_crlf_frontmatter_is_converted(self):
        with open(os.path.join(self.root, "wiki/crlf2.md"), "wb") as f:
            f.write(b"---\r\ntype: idea\r\nlayer: concept\r\n---\r\n\r\n# C\r\n\r\nsee [[alpha]]\r\n")
        mig.apply(self.root)
        with open(os.path.join(self.root, "wiki/crlf2.md"), "rb") as f:
            self.assertEqual(f.read(), b"---\r\ntype: idea\r\nlayer: concept\r\n---\r\n\r\n# C\r\n\r\nsee [Alpha one two](alpha.md)\r\n")


if __name__ == "__main__":
    unittest.main()
