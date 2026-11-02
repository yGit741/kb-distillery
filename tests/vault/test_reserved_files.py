"""wiki/index.md and wiki/log.md are the OKF reserved files of the bundle root: they are not pages anywhere."""
import os
import tempfile
import unittest

from kb_distillery.vault import links, schema

PAGE = "---\ntype: idea\nlayer: concept\ndescription: About alpha.\n---\n\n# Alpha\n\nBody.\n"


class ReservedFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        wiki = os.path.join(self.root, "wiki")
        os.makedirs(wiki)
        for name, text in (("alpha.md", PAGE), ("index.md", "---\nokf_version: 0.2\n---\n\n- [Alpha](alpha.md)\n"),
                           ("log.md", "# Log\n\n## 2026-10-22\n\n### ingest | alpha\n")):
            with open(os.path.join(wiki, name), "w", encoding="utf-8") as f:
                f.write(text)

    def test_is_page_file(self):
        self.assertTrue(schema.is_page_file("alpha.md"))
        for name in ("index.md", "log.md", "alpha.txt", "alpha.png"):
            self.assertFalse(schema.is_page_file(name), name)
        self.assertTrue(schema.is_page_file("log-book.md"))                      # only the exact reserved names

    def test_paths_name_the_bundle_root(self):
        self.assertEqual((schema.INDEX_REL, schema.LOG_REL), ("wiki/index.md", "wiki/log.md"))
        self.assertIn(schema.INDEX_REL, schema.GENERATED)
        self.assertEqual(schema.lane_of("wiki/index.md"), "knowledge")
        self.assertNotIn("index.md", schema.ROOT_MD)                             # a root index.md is no longer allowed
        self.assertEqual(set(schema.RESTORE_EXCLUDED), {"wiki/index.md", "wiki/log.md"})

    def test_titles_and_slug_scans_skip_them(self):
        self.assertEqual(links.read_titles(os.path.join(self.root, "wiki")), {"alpha": "Alpha"})

    def test_search_cards_skip_them(self):
        from kb_distillery.search import cards
        out = os.path.join(self.root, "cards")
        res = cards.build(os.path.join(self.root, "wiki"), out)
        self.assertEqual(sorted(os.listdir(out)), ["alpha.md"])
        self.assertEqual(res["cards"], 1)

    def test_loaders_skip_them(self):
        from kb_distillery.search import semfind
        self.assertEqual(sorted(semfind.load_pages(self.root)), ["alpha"])
        from kb_distillery.services import scopes as services_scopes
        self.assertEqual(sorted(services_scopes.load_pages(self.root)), ["alpha"])
        from kb_distillery.digest import pipeline
        self.assertEqual([p["slug"] if isinstance(p, dict) else p[0] for p in pipeline.load_pages(self.root)], ["alpha"])

    def test_the_agent_cannot_cite_them(self):
        from kb_distillery.services import chat_agent
        self.assertIsNone(chat_agent.slug_from_read({"file_path": os.path.join(chat_agent.WIKI, "index.md")}))
        self.assertIsNone(chat_agent.slug_from_read({"file_path": os.path.join(chat_agent.WIKI, "log.md")}))


if __name__ == "__main__":
    unittest.main()
