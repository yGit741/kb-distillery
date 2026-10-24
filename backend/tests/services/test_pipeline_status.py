"""Ingestion / digestion status rules and catalog failure logging (pure, no vault needed)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from kb.services import pipeline as dd
from kb.ingest import catalog


class StatusTest(unittest.TestCase):
    def test_ingestion(self):
        failed = {"raw/inbox/x.xyz": "no format"}
        self.assertEqual(dd._ingestion("raw/inbox/a.pdf", "queued", "", None, failed, set()), "inbox")
        self.assertEqual(dd._ingestion("raw/inbox/x.xyz", "queued", "", None, failed, set()), "failed")
        self.assertEqual(dd._ingestion("raw/images/a.png", "queued", "", None, failed, set()), "uncataloged")
        self.assertEqual(dd._ingestion("raw/printed-docs/a.pdf", "digested", "paper-a", None, failed, set()), "cataloged")
        self.assertEqual(dd._ingestion("raw/handwritten/a.pdf", "queued", "", 3, failed, set()), "cataloged")
        self.assertEqual(dd._ingestion("raw/emails/t/thread.md", "queued", "", None, failed, {"raw/emails/t"}), "cataloged")

    def test_digestion(self):
        self.assertEqual(dd._digestion("uncataloged", "queued", ""), "")
        self.assertEqual(dd._digestion("cataloged", "queued", ""), "not digested")
        self.assertEqual(dd._digestion("cataloged", "source", "listed"), "not digested")   # a stub is not a note
        self.assertEqual(dd._digestion("cataloged", "source", "full"), "digested")
        self.assertEqual(dd._digestion("cataloged", "partial", ""), "partial")
        self.assertEqual(dd._digestion("cataloged", "skip", ""), "skipped")

    def test_companions(self):
        self.assertEqual(dd._companion_of("raw/presentations/a (annotations).pdf", "presentations", "ink",
                                          "raw/presentations/a.pdf"), "raw/presentations/a.pdf")
        self.assertEqual(dd._companion_of("raw/emails/t/img.png", "emails", "queued", ""), "raw/emails/t/thread.md")
        self.assertEqual(dd._companion_of("raw/emails/t/thread.md", "emails", "queued", ""), "")
        self.assertEqual(dd._companion_of("raw/printed-docs/a.pdf", "printed-docs", "queued", ""), "")


class CatalogLogTest(unittest.TestCase):
    def test_failure_is_logged_with_reason(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        os.makedirs(os.path.join(tmp, "raw", "inbox"))
        open(os.path.join(tmp, "raw", "inbox", "odd.xyz"), "w").write("x")
        with mock.patch.object(catalog, "ROOT", tmp), \
                mock.patch.object(catalog, "CATALOG_LOG_DIR", os.path.join(tmp, "meta", ".catalog")):
            with self.assertRaises(ValueError):
                catalog.catalog("raw/inbox/odd.xyz")
        rows = [json.loads(l) for l in open(os.path.join(tmp, "meta", ".catalog", "failures.jsonl"))]
        self.assertEqual(rows[0]["path"], "raw/inbox/odd.xyz")
        self.assertIn("no format", rows[0]["reason"])


if __name__ == "__main__":
    unittest.main()
