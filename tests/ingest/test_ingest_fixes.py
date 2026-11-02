"""Tests: shared TLS helper, resolve arXiv gaps, non-arXiv PDF scrape + stub title, drain count,
to-read stubs."""
import hashlib
import json
import os
import ssl
import sys
import tempfile
import unittest
import urllib.request
from unittest.mock import patch, MagicMock


from kb_distillery.config import net
from kb_distillery.ingest import resolve, scrap, catalog


class TestNet(unittest.TestCase):
    def test_context_and_injected_opener(self):
        self.assertIsInstance(net.ssl_context(), ssl.SSLContext)
        seen = {}

        class Fake:
            def open(self, req, timeout=None):
                seen["req"] = req
                return "resp"

        with patch.object(net, "opener", lambda: Fake()):
            self.assertEqual(net.urlopen("http://x", timeout=3), "resp")
        self.assertEqual(seen["req"], "http://x")

    def test_install_sets_default_context(self):
        old = ssl._create_default_https_context
        try:
            net.install()
            self.assertIs(ssl._create_default_https_context, net.ssl_context)
        finally:
            ssl._create_default_https_context = old


PAGE = """---
type: paper
url: https://aclanthology.org/2024.x
{extra}---

# Why Are Sensitive Functions Hard

## Links out
{links}
"""


class VaultCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "wiki"))
        os.makedirs(os.path.join(self.root, "raw", "inbox"))
        for mod in (resolve, scrap, catalog):
            p = patch.object(mod, "ROOT", self.root)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(resolve, "WIKI_DIR", "wiki")
        p.start(); self.addCleanup(p.stop)
        p = patch.object(resolve, "walk", lambda d, ext=None: sorted(
            f"wiki/{n}" for n in os.listdir(os.path.join(self.root, "wiki"))))
        p.start(); self.addCleanup(p.stop)
        p = patch.object(scrap, "INBOX", os.path.join(self.root, "raw", "inbox"))
        p.start(); self.addCleanup(p.stop)
        p = patch.object(resolve, "read_manifest", lambda: {})
        p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def page(self, slug, extra="", links="- Concepts: [[]]"):
        with open(os.path.join(self.root, "wiki", f"{slug}.md"), "w") as f:
            f.write(PAGE.format(extra=extra, links=links))


class TestResolveArxiv(VaultCase):
    def test_arxiv_key(self):
        self.page("paper-2024-a", extra="arxiv: 2402.09963\n")
        r = resolve.resolve("arxiv:2402.09963")
        self.assertEqual(r.status, "found")

    def test_arxiv_key_url_form(self):
        self.page("paper-2024-a", extra="arxiv: https://arxiv.org/abs/2402.09963v2\n")
        self.assertEqual(resolve.resolve("2402.09963").status, "found")

    def test_links_out(self):
        self.page("paper-2024-a", links="- arXiv: https://arxiv.org/abs/2402.09963")
        self.assertEqual(resolve.resolve("2402.09963").status, "found")

    def test_title_fallback_online_and_offline(self):
        self.page("paper-2024-a")
        with patch.object(resolve, "arxiv_title", lambda a: "Why are sensitive functions hard"):
            self.assertEqual(resolve.resolve("2402.09963").status, "found")
        with patch.object(resolve, "arxiv_title", lambda a: None):
            self.assertEqual(resolve.resolve("2402.09963").status, "not_found")

    def test_arxiv_title_offline_flag(self):
        with patch.dict(os.environ, {"KB_OFFLINE": "1"}):
            self.assertIsNone(resolve.arxiv_title("2402.09963"))


class TestScrapPdf(VaultCase):
    def test_pdf_url_takes_articles_branch_and_records_source(self):
        data = b"%PDF-1.4 fake"
        url = "https://example.org/papers/Threshold.PDF"
        with patch.object(scrap, "_check_pre_resolve"), \
             patch.object(scrap, "_check_post_bytes"), \
             patch.object(scrap, "_download", lambda u, d: (open(d, "wb").write(data), data)[1]):
            rel = scrap.scrap(url)
        self.assertTrue(rel.endswith(".pdf"))
        self.assertEqual(scrap.source_url(os.path.join(self.root, rel)), url)

    def test_html_at_pdf_url_refused(self):
        with patch.object(scrap, "_check_pre_resolve"), \
             patch.object(scrap, "_download", lambda u, d: (open(d, "wb").write(b"<html>"), b"<html>")[1]):
            with self.assertRaises(ValueError):
                scrap.scrap("https://example.org/x.pdf")


class TestStub(unittest.TestCase):
    def test_fallback_title_strips_prefix_and_year(self):
        s = catalog._catalog_stub("paper-1997-threshold-intervals-under-group-symmetries", "raw/x.pdf")
        self.assertIn("# Threshold Intervals Under Group Symmetries\n", s)

    def test_stub_writes_neither_a_title_nor_sources_the_heading_and_url_already_say(self):
        s = catalog._catalog_stub("paper-1997-x", "raw/x.pdf", title="X Paper", url="https://example.org/x")
        head = s.split("\n---\n", 1)[0]
        self.assertIn("url: https://example.org/x", head)
        self.assertNotIn("title:", head)
        self.assertNotIn("sources:", head)
        self.assertIn("\n# X Paper\n", s)

    def test_catalog_paper_url_and_title(self):
        with tempfile.TemporaryDirectory() as root:
            for d in ("wiki", "raw/inbox", "raw/printed-docs"):
                os.makedirs(os.path.join(root, d))
            inbox = os.path.join(root, "raw", "inbox", "thr.pdf")
            with open(inbox, "wb") as f:
                f.write(b"%PDF-1.4 x")
            with open(os.path.join(root, "raw", "inbox", ".keep"), "w"):
                pass
            os.makedirs(os.path.join(root, "meta", ".catalog"))
            with open(os.path.join(root, "meta", ".catalog", "sources.jsonl"), "w") as f:
                f.write(json.dumps({"file": "thr.pdf", "sha1": hashlib.sha1(b"%PDF-1.4 x").hexdigest(),
                                    "url": "https://example.org/thr.pdf"}) + "\n")
            with patch.object(catalog, "ROOT", root), patch.object(catalog, "_run_lint", lambda: None), \
                 patch("kb_distillery.ingest.scrap.ROOT", root), patch.object(catalog, "set_collection", lambda *a: None):
                dest, slug = catalog.catalog_paper("raw/inbox/thr.pdf",
                                                   title="Threshold Intervals Under Group Symmetries",
                                                   year="1997")
            self.assertEqual(dest, "raw/printed-docs/1997-threshold-intervals-under-group-symmetries.pdf")
            text = open(os.path.join(root, "wiki", f"{slug}.md")).read()
            self.assertIn("url: https://example.org/thr.pdf", text)
            self.assertIn("# Threshold Intervals Under Group Symmetries", text)


class TestDrainCount(unittest.TestCase):
    def test_items_not_paths(self):
        from kb_distillery.ops.wrap import _items
        paths = ["raw/printed-docs/2020-a.pdf", "wiki/paper-2020-a.md", "wiki/paper-2021-b.md",
                 "raw/printed-docs/2021-b.pdf", "meta/corpus.tsv", "index.md", "wiki/index.md", "wiki/log.md"]
        self.assertEqual(_items(paths), 2)
        self.assertEqual(_items(["meta/corpus.tsv"]), 1)


class WebClipNameTests(unittest.TestCase):
    def test_url_derived(self):
        from kb_distillery.ingest.scrap import web_clip_name
        self.assertEqual(web_clip_name("https://gilkalai.wordpress.com/ai-for-mathematics-spring-2027/"),
                         "gilkalai-wordpress-com-ai-for-mathematics-spring-2027.html")
        self.assertEqual(web_clip_name("https://www.windowsontheory.org/2023/12/22/emergent-abilities/"),
                         "windowsontheory-org-2023-12-22-emergent-abilities.html")
        self.assertEqual(web_clip_name("https://example.org/"), "example-org.html")
        self.assertEqual(web_clip_name(""), "page.html")
        self.assertLessEqual(len(web_clip_name("https://a.org/" + "x" * 500)), 125)


if __name__ == "__main__":
    unittest.main()

