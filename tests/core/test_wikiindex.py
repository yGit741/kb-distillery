"""The generated wiki index is a tiny root plus one reserved `index.md` per type (per year for a big type); a section
index is never a page, a node, a card or a search hit."""
import os
import tempfile
import unittest
from unittest import mock

from kb_distillery.core import links, schema, wikiindex
from kb_distillery.lint import okf_check

PAGE = "---\ntype: {type}\nlayer: source\n{extra}description: About {slug}.\n---\n\n# Title of {slug}\n\nBody.\n"


def entry(slug, type_="paper", year=None, summary=""):
    return {"slug": slug, "type": type_, "title": f"Title of {slug}", "summary": summary or f"About {slug}.", "year": year}


class Render(unittest.TestCase):
    def test_root_has_one_line_per_type_and_links_the_section(self):
        files = wikiindex.render([entry("a"), entry("b"), entry("c", "idea")])
        root = files["wiki/index.md"]
        self.assertTrue(root.startswith("---\nokf_version: 0.2\n---\n"))
        self.assertIn("- [Ideas](idea/index.md) — 1 page.", root)
        self.assertIn("- [Papers](paper/index.md) — 2 pages.", root)
        self.assertNotIn("slug", root)
        self.assertNotIn("](a.md)", root)                                  # the root lists no page
        self.assertEqual(sorted(files), ["wiki/idea/index.md", "wiki/index.md", "wiki/paper/index.md"])

    def test_section_rows_link_up_one_folder(self):
        text = wikiindex.render([entry("a")])["wiki/paper/index.md"]
        self.assertIn("- [Title of a](../a.md) — About a.", text)
        self.assertIn("[wiki index](../index.md)", text)
        self.assertEqual(links.page_path("a", 2), "../../a.md")

    def test_a_big_type_splits_by_year_newest_first_and_undated_last(self):
        with mock.patch.object(wikiindex, "SECTION_MAX_BYTES", 100):
            files = wikiindex.render([entry("a", year="2019"), entry("b", year="2021"), entry("c", year="2021"), entry("d")])
        self.assertEqual(sorted(files), ["wiki/index.md", "wiki/paper/2019/index.md", "wiki/paper/2021/index.md",
                                         "wiki/paper/index.md", "wiki/paper/undated/index.md"])
        top = files["wiki/paper/index.md"]
        self.assertLess(top.index("2021/index.md"), top.index("2019/index.md"))
        self.assertLess(top.index("2019/index.md"), top.index("undated/index.md"))
        self.assertIn("[2021](2021/index.md) — 2 pages", top)
        self.assertIn("- [Title of b](../../b.md)", files["wiki/paper/2021/index.md"])
        self.assertIn("[wiki index](../../index.md)", files["wiki/paper/2021/index.md"])
        self.assertIn("4 pages, by year", files["wiki/index.md"])

    def test_types_outside_the_builtin_list_follow_the_kb_order(self):
        files = wikiindex.render([entry("a", "skill"), entry("b", "company")], labels={"skill": "Skill", "company": "Company"},
                                 order=["company", "skill"])
        root = files["wiki/index.md"]
        self.assertLess(root.index("[Company]"), root.index("[Skill]"))

    def test_page_year(self):
        self.assertEqual(wikiindex.page_year({"year": 1996}), "1996")
        self.assertEqual(wikiindex.page_year({"created": "2025-04-19T00:00:00Z"}), "2025")
        self.assertIsNone(wikiindex.page_year({"year": "n.d."}))
        self.assertIsNone(wikiindex.page_year({}))


class IndexPaths(unittest.TestCase):
    def test_which_paths_are_generated_indexes(self):
        for rel in ("wiki/index.md", "wiki/paper/index.md", "wiki/blog-post/2019/index.md", "wiki/mail/undated/index.md"):
            self.assertTrue(schema.is_index_path(rel), rel)
            self.assertTrue(schema.is_generated(rel), rel)
        for rel in ("wiki/paper/other.md", "wiki/a/b/c/index.md", "wiki/Paper/index.md", "index.md", "raw/x/index.md",
                    "examples/demo/wiki/paper/index.md", "wiki/paper.md"):
            self.assertFalse(schema.is_index_path(rel), rel)
        self.assertTrue(schema.is_generated("meta/corpus.tsv"))

    def test_the_section_index_is_not_a_page_by_name(self):
        self.assertFalse(schema.is_page_file("index.md"))
        self.assertTrue(okf_check.is_reserved("wiki/paper/2019/index.md"))


class OnDisk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "wiki"))

    def put(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel))

    def test_write_then_stale_section_indexes_and_their_folders_go_but_nothing_else(self):
        with mock.patch.object(wikiindex, "SECTION_MAX_BYTES", 100):
            wikiindex.write(self.root, wikiindex.render([entry("a", year="2019"), entry("b", year="2021")]))
        self.assertTrue(self.exists("wiki/paper/2019/index.md"))
        self.put("wiki/paper/notes.txt", "mine")                                   # not generated: stays
        self.put("wiki/idea/index.md", "# my own file, no marker\n")              # not generated: stays
        wikiindex.write(self.root, wikiindex.render([entry("a", year="2019"), entry("b", year="2021")]))
        wikiindex.write(self.root, wikiindex.render([entry("a")]))                # small again: years go
        self.assertFalse(self.exists("wiki/paper/2019/index.md"))
        self.assertFalse(self.exists("wiki/paper/2019"))
        self.assertTrue(self.exists("wiki/paper/index.md"))
        self.assertTrue(self.exists("wiki/paper/notes.txt"))
        self.assertTrue(self.exists("wiki/idea/index.md"))
        wikiindex.write(self.root, wikiindex.render([]))                           # every page gone
        self.assertFalse(self.exists("wiki/paper/index.md"))
        self.assertTrue(self.exists("wiki/paper"))                                 # still holds notes.txt
        self.assertTrue(self.exists("wiki/index.md"))

    def test_parse_rows_reads_every_section(self):
        wikiindex.write(self.root, wikiindex.render([entry("a", summary="x — y"), entry("b", "idea")]))
        rows = wikiindex.parse_rows(self.root)
        self.assertEqual(sorted(rows), ["a", "b"])
        self.assertEqual(rows["a"]["section"], "Papers")
        self.assertEqual(rows["a"]["summary"], "x — y")
        self.assertEqual(rows["b"]["title"], "Title of b")

    def test_a_page_whose_slug_ends_in_index_is_a_row_not_a_section_link(self):
        wikiindex.write(self.root, wikiindex.render([entry("h-index"), entry("index-notes")]))
        self.assertEqual(sorted(wikiindex.parse_rows(self.root)), ["h-index", "index-notes"])

    def test_sizes_and_typical_query(self):
        wikiindex.write(self.root, wikiindex.render([entry("a"), entry("b", "idea")]))
        sz = wikiindex.sizes(self.root)
        self.assertEqual(sorted(sz), ["wiki/idea/index.md", "wiki/index.md", "wiki/paper/index.md"])
        want = sz["wiki/index.md"] + (sz["wiki/idea/index.md"] + sz["wiki/paper/index.md"]) / 2 + 5 * 1000
        self.assertAlmostEqual(wikiindex.typical_query_bytes(self.root, 1000), want)


class SubfolderIndexIsNeverAPage(unittest.TestCase):
    """A section index below wiki/ must not become a page, a graph node, a search card, a scope page or a hit."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        wiki = os.path.join(self.root, "wiki")
        for slug in ("a", "b"):
            os.makedirs(wiki, exist_ok=True)
            with open(os.path.join(wiki, f"{slug}.md"), "w", encoding="utf-8") as f:
                f.write(PAGE.format(type="idea", slug=slug, extra=""))
        files = wikiindex.render([entry("a", "idea"), entry("b", "idea", year="2020")])
        wikiindex.write(self.root, files)
        os.makedirs(os.path.join(wiki, "idea", "2020"), exist_ok=True)
        with open(os.path.join(wiki, "idea", "2020", "index.md"), "w", encoding="utf-8") as f:
            f.write("# Ideas — 2020\n\n- [Title of b](../../b.md)\n")

    def test_lint_page_walkers(self):
        from kb_distillery.lint import lint
        with mock.patch.object(lint, "ROOT", self.root):
            self.assertEqual(lint.wiki_page_files(), ["wiki/a.md", "wiki/b.md"])
            self.assertEqual(sorted(lint.load_wiki_pages()), ["a", "b"])

    def test_titles_cards_and_loaders(self):
        self.assertEqual(sorted(links.read_titles(os.path.join(self.root, "wiki"))), ["a", "b"])
        from kb_distillery.search import cards, semfind
        out = os.path.join(self.root, "cards")
        self.assertEqual(cards.build(os.path.join(self.root, "wiki"), out)["cards"], 2)
        self.assertEqual(sorted(os.listdir(out)), ["a.md", "b.md"])
        self.assertEqual(sorted(semfind.load_pages(self.root)), ["a", "b"])
        from kb_distillery.services import scopes as services_scopes
        self.assertEqual(sorted(services_scopes.load_pages(self.root)), ["a", "b"])

    def test_the_graph_inputs_have_no_index_node(self):
        from kb_distillery.core import graph
        from kb_distillery.lint import lint
        with mock.patch.object(lint, "ROOT", self.root):
            pages = lint.load_wiki_pages()
        self.assertEqual(sorted(pages), ["a", "b"])
        self.assertEqual(sorted(graph.inbound_index(pages)), ["a", "b"])

    def test_okf_check_counts_two_pages_and_checks_the_index_links(self):
        findings, count = okf_check.check(self.root)
        self.assertEqual(count, 2)
        self.assertEqual(findings, {})
        with open(os.path.join(self.root, "wiki", "idea", "2020", "index.md"), "a", encoding="utf-8") as f:
            f.write("- [Gone](../../gone.md)\n")
        findings, count = okf_check.check(self.root)
        self.assertEqual(count, 2)
        self.assertEqual([r for r, _m in findings["wiki/idea/2020/index.md"]], ["link"])

    def test_the_agent_cannot_cite_a_section_index(self):
        from kb_distillery.services import chat_agent
        self.assertIsNone(chat_agent.slug_from_read({"file_path": os.path.join(chat_agent.WIKI, "idea", "index.md")}))


if __name__ == "__main__":
    unittest.main()
