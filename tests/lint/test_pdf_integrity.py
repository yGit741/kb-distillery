"""PDF integrity: old-style arXiv IDs resolve, and saved web pages never pass as PDFs.

Regression for the ada-example bibliography, where three arXiv/AMS landing pages were
saved as .pdf and sat in the corpus as `digested`.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

from kb_distillery.config.paths import vault_root
META = os.path.join(vault_root(), "meta")

from kb_distillery.lint import lint
from kb_distillery.ingest import resolve, scrap

HTML = b"<!DOCTYPE html>\n<html><head><title>arXiv</title></head><body>abstract page</body></html>"
PDF = b"%PDF-1.5\n%fake but well-formed header\n"


class ArxivIdTests(unittest.TestCase):
    def test_new_style(self):
        self.assertEqual(resolve.normalize_arxiv_id("https://arxiv.org/abs/1906.05890v3"), "1906.05890")
        self.assertEqual(resolve.normalize_arxiv_id("2105.10386"), "2105.10386")

    def test_old_style(self):
        cases = {
            "https://arxiv.org/abs/math/9811157": "math/9811157",
            "https://arxiv.org/abs/math/9811157v2": "math/9811157",
            "https://arxiv.org/pdf/math.PR/0503503": "math.PR/0503503",
            "https://arxiv.org/abs/hep-th/9901001": "hep-th/9901001",
            "quant-ph/0101012": "quant-ph/0101012",
        }
        for url, want in cases.items():
            with self.subTest(url=url):
                self.assertEqual(resolve.normalize_arxiv_id(url), want)

    def test_non_arxiv(self):
        self.assertIsNone(resolve.normalize_arxiv_id("https://example.com/paper.pdf"))


class LintMagicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "raw", "papers", "x"))
        lint.errors = []

    def _put(self, name, data):
        rel = f"raw/papers/x/{name}"
        with open(os.path.join(self.tmp, rel), "wb") as f:
            f.write(data)
        return rel

    def test_html_saved_as_pdf_is_an_error(self):
        rel = self._put("1998-fake.pdf", HTML)
        with mock.patch.object(lint, "ROOT", self.tmp):
            lint.check_pdf_magic([rel])
        self.assertEqual(len(lint.errors), 1)
        self.assertIn("not a PDF", str(lint.errors[0]))

    def test_real_pdf_passes(self):
        rel = self._put("1998-real.pdf", PDF)
        with mock.patch.object(lint, "ROOT", self.tmp):
            lint.check_pdf_magic([rel])
        self.assertEqual(lint.errors, [])

    def test_non_pdf_files_ignored(self):
        rel = self._put("notes.md", HTML)
        with mock.patch.object(lint, "ROOT", self.tmp):
            lint.check_pdf_magic([rel])
        self.assertEqual(lint.errors, [])


class ScrapMagicTests(unittest.TestCase):
    def setUp(self):
        self.inbox = tempfile.mkdtemp()

    def _scrap(self, payload):
        def fake_download(url, dest):
            with open(dest, "wb") as f:
                f.write(payload)
            return payload
        with mock.patch.object(scrap, "INBOX", self.inbox), \
             mock.patch.object(scrap, "_download", side_effect=fake_download), \
             mock.patch.object(scrap, "_check_post_bytes"):
            return scrap.scrap("https://arxiv.org/abs/math/9811157", force=True)

    def test_html_response_is_refused_and_not_saved(self):
        with self.assertRaises(ValueError) as ctx:
            self._scrap(HTML)
        self.assertIn("HTML page", str(ctx.exception))
        self.assertEqual(os.listdir(self.inbox), [], "a rejected download must leave nothing behind")

    def test_pdf_response_is_saved_with_old_style_name(self):
        rel = self._scrap(PDF)
        self.assertEqual(rel, "raw/inbox/arxiv-math_9811157.pdf")
        self.assertEqual(os.listdir(self.inbox), ["arxiv-math_9811157.pdf"])


class ScrapNameRoundTripTests(unittest.TestCase):
    """scrap names a file from the id; catalog must recover exactly that id."""

    def test_round_trip(self):
        from kb_distillery.ingest.catalog import _arxiv_id_from_scrape
        for aid in ["2105.10386", "1906.05890", "math/9811157", "math.PR/0503503",
                    "hep-th/9901001", "quant-ph/0101012", "cond-mat.stat-mech/0601001"]:
            name = scrap.arxiv_filename(aid)
            with self.subTest(aid=aid):
                self.assertEqual(_arxiv_id_from_scrape(name), aid)

    def test_not_an_arxiv_scrape(self):
        from kb_distillery.ingest.catalog import _arxiv_id_from_scrape
        self.assertIsNone(_arxiv_id_from_scrape("paper.pdf"))


ATOM_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2101.08303v2</id>
    <published>2021-01-20T00:00:00Z</published>
    <title>From Local Pseudorandom Generators to
      Hardness of Learning</title>
    <author><name>Amit Daniely</name></author>
    <author><name>Gal Vardi</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2106.03875v1</id>
    <published>2021-06-07T00:00:00Z</published>
    <title>Bayesian-Wilson coefficients in lattice QCD computations</title>
    <author><name>Somebody Else</name></author>
  </entry>
</feed>"""


class ArxivMetaTests(unittest.TestCase):
    def test_parse_atom(self):
        from kb_distillery.ingest import arxiv_meta
        got = arxiv_meta._parse(ATOM_FIXTURE)
        rec = got["2101.08303"]
        self.assertEqual(rec["authors"], ["Amit Daniely", "Gal Vardi"])
        self.assertEqual(rec["year"], 2021)
        self.assertEqual(rec["title"], "From Local Pseudorandom Generators to Hardness of Learning")

    def test_wrong_paper_is_never_adopted(self):
        """The bootstrap left fabricated arXiv ids; a stranger's record must not overwrite a page."""
        from kb_distillery.ingest import arxiv_meta
        from kb_distillery.ingest.sources.researcher import backfill
        fetched = arxiv_meta._parse(ATOM_FIXTURE)
        rows = [
            ("ok.md", "2101.08303", ["Amit Daniely"], "From Local Pseudorandom Generators to Hardness of Learning"),
            ("bad.md", "2106.03875", ["Gal Vardi"], "On the Optimal Memorization Power of ReLU Neural Networks"),
        ]
        updates, _same, mismatched, _missing = backfill.plan(rows, fetched)
        self.assertEqual([u[0] for u in updates], ["ok.md"])
        self.assertEqual(updates[0][2], ["Amit Daniely", "Gal Vardi"])
        self.assertEqual([m[0] for m in mismatched], ["bad.md"])

    def test_title_search_needs_both_signals(self):
        """Title alone or author alone is not enough to accept a search hit."""
        from kb_distillery.ingest import arxiv_meta

        class Resp:
            def __init__(self, data): self.data = data
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return self.data

        opener = lambda *_a, **_k: Resp(ATOM_FIXTURE)
        slept = []
        self.enterContext(mock.patch.object(arxiv_meta, "SLEEP", slept.append))   # arXiv's 3s politeness pause, not under test
        title = "From Local Pseudorandom Generators to Hardness of Learning"
        self.assertIsNotNone(arxiv_meta.search_title(title, ["Gal Vardi"], opener=opener))
        self.assertIsNone(arxiv_meta.search_title(title, ["Nadav Cohen"], opener=opener))
        self.assertIsNone(arxiv_meta.search_title("Tensor rank of convolutional circuits",
                                                  ["Gal Vardi"], opener=opener))

    def test_author_names_safe_for_flat_yaml(self):
        from kb_distillery.ingest.sources.researcher import backfill
        self.assertEqual(backfill.format_authors(["Ryan O'Donnell", "Smith, Jr.", "A#B"]),
                         "[Ryan O'Donnell, Smith Jr., AB]")


if __name__ == "__main__":
    unittest.main()
