"""arXiv integrity: the API is never guessed around, and a PDF must be the paper its page cites.

Regression for 2026-10-22: 35 paper PDFs were downloaded from Semantic Scholar arXiv ids that
pointed at strangers' papers and sat as `digested`; a 429 during `drain-inbox` filed Belkin's
"Fit without fear" as `2000-untitled.pdf`, which then blocked three more files; and
`rename_raw.py` refused to run because of four stale rows.
"""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import contextmanager
from unittest import mock

from kb.paths import vault_root
META = os.path.join(vault_root(), "meta")

from kb.lint import lint
from kb.maintenance import rename_raw
from kb.ingest import arxiv_meta, backfill, catalog, researcher

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>"""
ENTRY = """<entry><id>http://arxiv.org/abs/{id}v1</id><title>{title}</title>
<published>{year}-01-01T00:00:00Z</published>{authors}</entry>"""


def feed(*records):
    entries = "".join(
        ENTRY.format(id=i, title=t, year=y, authors="".join(f"<author><name>{a}</name></author>" for a in aa))
        for i, t, y, aa in records)
    return ATOM.format(entries=entries).encode()


@contextmanager
def _resp(data):
    yield io.BytesIO(data)


def http_error(code, retry_after=None):
    headers = {"Retry-After": str(retry_after)} if retry_after else {}
    return urllib.error.HTTPError("u", code, "x", headers, None)


class FetchRetryTests(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        self._sleep = mock.patch.object(arxiv_meta, "SLEEP", self.sleeps.append)
        self._sleep.start()
        arxiv_meta._last_call = 0.0

    def tearDown(self):
        self._sleep.stop()

    def test_429_then_success(self):
        answers = [http_error(429, retry_after=7), feed(("1611.03530", "Rethinking", 2016, ["Zhang"]))]

        def opener(req, timeout):
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return _resp(a)

        out = arxiv_meta.fetch(["1611.03530"], opener=opener, strict=True)
        self.assertEqual(out["1611.03530"]["title"], "Rethinking")
        self.assertIn(7.0, self.sleeps)                      # honoured Retry-After

    def test_strict_raises_after_retries(self):
        def opener(req, timeout):
            raise http_error(429)
        with self.assertRaises(arxiv_meta.ArxivUnavailable):
            arxiv_meta.fetch(["1611.03530"], opener=opener, strict=True)

    def test_lenient_returns_partial(self):
        def opener(req, timeout):
            raise http_error(503)
        self.assertEqual(arxiv_meta.fetch(["1611.03530"], opener=opener), {})

    def test_non_retryable_is_unavailable_at_once(self):
        calls = []

        def opener(req, timeout):
            calls.append(1)
            raise http_error(404)
        with self.assertRaises(arxiv_meta.ArxivUnavailable):
            arxiv_meta.fetch(["x"], opener=opener, strict=True)
        self.assertEqual(len(calls), 1)

    def test_search_propagates_unavailable(self):
        def opener(req, timeout):
            raise http_error(429)
        with self.assertRaises(arxiv_meta.ArxivUnavailable):
            arxiv_meta.search_title("Benign overfitting in linear regression", ["Bartlett"], opener=opener)

    def test_throttle_spaces_calls(self):
        def opener(req, timeout):
            return _resp(feed())
        arxiv_meta.fetch(["a"], opener=opener)
        arxiv_meta.fetch(["b"], opener=opener)
        self.assertTrue(any(0 < s <= arxiv_meta.PAUSE_S for s in self.sleeps))


class StampTests(unittest.TestCase):
    def test_margin_stamp_only(self):
        self.assertEqual(arxiv_meta.STAMP.search("arXiv:2306.09994v2 [math.OA] 8 Aug 2023").group(1), "2306.09994")
        self.assertEqual(arxiv_meta.STAMP.search("arXiv:math/9811157v1 [math.CO] 2 Nov 1998").group(1), "math/9811157")
        self.assertIsNone(arxiv_meta.STAMP.search("see arXiv:2306.09994 for the proof"))

    def test_stamp_reads_page_one(self):
        with mock.patch.dict(sys.modules, {"fitz": mock.MagicMock()}) as mods:
            doc = mods["fitz"].open.return_value
            doc.page_count = 1
            doc.__getitem__.return_value.get_text.return_value = "QUANTUM MYCIELSKI\narXiv:2306.09994v2 [math.OA] 8 Aug 2023"
            self.assertEqual(arxiv_meta.stamp("/x.pdf"), "2306.09994")


class CatalogRefusesOnOutage(unittest.TestCase):
    def test_lookup_raises_value_error_not_untitled(self):
        with mock.patch.object(arxiv_meta, "fetch", side_effect=arxiv_meta.ArxivUnavailable("HTTP 429")):
            with self.assertRaises(ValueError) as cm:
                catalog._arxiv_lookup("arxiv-2105-14368.pdf")
        self.assertIn("left in inbox", str(cm.exception))
        self.assertIn("2105.14368", str(cm.exception))


class VerifiedArxivTests(unittest.TestCase):
    PAPER = {"arxiv": "2306.09994", "title": "Benign Overfitting and Grokking in ReLU Networks for XOR Cluster Data",
             "authors": ["Zhiwei Xu", "Gal Vardi"]}

    def test_scholar_id_accepted_when_same_paper(self):
        fetch = lambda ids, strict=False: {"2306.09994": {"id": "2306.09994", "title": self.PAPER["title"], "authors": ["Gal Vardi"]}}
        search = mock.Mock()
        self.assertEqual(researcher.verified_arxiv(self.PAPER, ["Gal Vardi"], fetch, search), ("2306.09994", "ok"))
        search.assert_not_called()

    def test_wrong_scholar_id_fixed_by_title(self):
        fetch = lambda ids, strict=False: {"2306.09994": {"id": "2306.09994", "title": "Quantum Mycielski graphs", "authors": ["A. Bochniak"]}}
        search = lambda title, authors: {"id": "2310.02541", "title": self.PAPER["title"], "authors": ["Gal Vardi"]}
        self.assertEqual(researcher.verified_arxiv(self.PAPER, ["Gal Vardi"], fetch, search), ("2310.02541", "fixed"))

    def test_wrong_id_and_no_match_is_skipped(self):
        fetch = lambda ids, strict=False: {"2306.09994": {"id": "2306.09994", "title": "Quantum Mycielski graphs", "authors": ["A. Bochniak"]}}
        self.assertEqual(researcher.verified_arxiv(self.PAPER, ["Gal Vardi"], fetch, lambda t, a: None), (None, "mismatch"))

    def test_outage_propagates(self):
        def fetch(ids, strict=False):
            raise arxiv_meta.ArxivUnavailable("HTTP 429")
        with self.assertRaises(arxiv_meta.ArxivUnavailable):
            researcher.verified_arxiv(self.PAPER, ["Gal Vardi"], fetch, mock.Mock())


class WrongDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "wiki"))
        os.makedirs(os.path.join(self.tmp, "raw", "printed-docs"))
        self.raw = "raw/printed-docs/2024-xor.pdf"
        with open(os.path.join(self.tmp, self.raw), "wb") as f:
            f.write(b"%PDF-1.5 wrong")
        self.page = os.path.join(self.tmp, "wiki", "paper-2024-xor.md")
        with open(self.page, "w", encoding="utf-8") as f:
            f.write(f"---\ntype: paper\nurl: https://arxiv.org/abs/2310.02541\nraw: {self.raw}\n---\n\n# XOR\n")

    def _patch(self):
        return mock.patch.multiple(backfill, ROOT=self.tmp, WIKI=os.path.join(self.tmp, "wiki"))

    def test_lists_mismatch(self):
        with self._patch():
            rows = backfill.wrong_downloads(stamp=lambda p: "2306.09994")
        self.assertEqual([(r[1], r[2], r[3]) for r in rows], [(self.raw, "2310.02541", "2306.09994")])

    def test_matching_or_unstamped_is_clean(self):
        with self._patch():
            self.assertEqual(backfill.wrong_downloads(stamp=lambda p: "2310.02541"), [])
            self.assertEqual(backfill.wrong_downloads(stamp=lambda p: None), [])

    def test_dry_run_replaces_nothing(self):
        with self._patch():
            code = backfill.refetch_raw(dry_run=True, stamp=lambda p: "2306.09994", downloader=mock.Mock())
        self.assertEqual(code, 1)
        self.assertEqual(open(os.path.join(self.tmp, self.raw), "rb").read(), b"%PDF-1.5 wrong")

    def test_apply_replaces_only_a_verified_pdf(self):
        stamps = {os.path.join(self.tmp, self.raw): "2306.09994"}

        def stamp(p):
            return stamps.get(p, "2310.02541")      # the fetched tmp file carries the right stamp

        def download(url, dest):
            self.assertEqual(url, "https://arxiv.org/pdf/2310.02541")
            with open(dest, "wb") as f:
                f.write(b"%PDF-1.5 right")
            return b"%PDF-1.5 right"
        with self._patch():
            code = backfill.refetch_raw(dry_run=False, stamp=stamp, downloader=download)
        self.assertEqual(code, 0)
        self.assertEqual(open(os.path.join(self.tmp, self.raw), "rb").read(), b"%PDF-1.5 right")

    def test_apply_keeps_old_bytes_when_fetch_is_wrong(self):
        def download(url, dest):
            with open(dest, "wb") as f:
                f.write(b"%PDF-1.5 other")
            return b"%PDF-1.5 other"
        with self._patch():
            code = backfill.refetch_raw(dry_run=False, stamp=lambda p: "2306.09994", downloader=download)
        self.assertEqual(code, 1)
        self.assertEqual(open(os.path.join(self.tmp, self.raw), "rb").read(), b"%PDF-1.5 wrong")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, self.raw + ".refetch")))


class LintStampTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "raw", "printed-docs"))
        self.raw = "raw/printed-docs/2024-xor.pdf"
        with open(os.path.join(self.tmp, self.raw), "wb") as f:
            f.write(b"%PDF-1.5")
        lint.warnings = []

    def _pages(self, url="https://arxiv.org/abs/2310.02541"):
        return {"paper-2024-xor": ("wiki/paper-2024-xor.md", {"type": "paper", "url": url, "raw": self.raw}, "")}

    def test_warns_and_caches(self):
        cache = os.path.join(self.tmp, ".cache", "arxiv-stamps.json")
        with mock.patch.multiple(lint, ROOT=self.tmp, STAMP_CACHE=cache), \
                mock.patch.object(lint.arxiv_meta, "stamp", return_value="2306.09994") as st:
            self.assertEqual(lint.check_arxiv_stamps(self._pages()), 1)
            self.assertEqual(lint.check_arxiv_stamps(self._pages()), 1)
            self.assertEqual(st.call_count, 1)                   # second run came from the cache
        self.assertIn("wrong download", lint.warnings[0])
        self.assertEqual(json.load(open(cache))[self.raw][1], "2306.09994")

    def test_silent_when_consistent(self):
        with mock.patch.multiple(lint, ROOT=self.tmp, STAMP_CACHE=os.path.join(self.tmp, "c.json")), \
                mock.patch.object(lint.arxiv_meta, "stamp", return_value="2310.02541"):
            self.assertEqual(lint.check_arxiv_stamps(self._pages()), 0)
        self.assertEqual(lint.warnings, [])


class RenameStaleRowsTests(unittest.TestCase):
    def test_stale_rows_skip_not_block(self):
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "raw", "printed-docs"))
        open(os.path.join(tmp, "raw", "printed-docs", "2000-untitled.pdf"), "wb").close()
        rows = [("raw/papers/old/2000-gone.pdf", "raw/papers/old/2000-gone-too.pdf", []),
                ("raw/printed-docs/2000-untitled.pdf", "raw/printed-docs/2021-fit-without-fear.pdf", [])]
        with mock.patch.object(rename_raw, "ROOT", tmp):
            errors, stale = rename_raw.validate(rows)
        self.assertEqual(errors, [])
        self.assertEqual(stale, ["raw/papers/old/2000-gone.pdf"])


if __name__ == "__main__":
    unittest.main()
