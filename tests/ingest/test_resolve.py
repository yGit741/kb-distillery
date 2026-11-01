"""Tests for kb_distillery.ingest.resolve and scrap dedup."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


from kb_distillery.ingest.resolve import (  # noqa: E402
    DuplicateBlocked,
    build_indexes,
    exit_code,
    find_by_sha1,
    normalize_arxiv_id,
    resolve,
    sha1_bytes,
)
from kb_distillery.ingest import scrap


class TestNormalizeArxiv(unittest.TestCase):
    def test_abs_url(self):
        self.assertEqual(normalize_arxiv_id("https://arxiv.org/abs/2306.13185"), "2306.13185")

    def test_abs_url_with_version(self):
        self.assertEqual(normalize_arxiv_id("https://arxiv.org/abs/2306.13185v2"), "2306.13185")

    def test_bare_id(self):
        self.assertEqual(normalize_arxiv_id("2306.13185v3"), "2306.13185")

    def test_filename(self):
        self.assertEqual(normalize_arxiv_id("arxiv-2306-13185.pdf"), "2306.13185")

    def test_none(self):
        self.assertIsNone(normalize_arxiv_id("not-an-arxiv-id"))


class TestResolveLogic(unittest.TestCase):
    def test_exit_codes(self):
        from kb_distillery.ingest.resolve import ResolveResult
        self.assertEqual(exit_code(ResolveResult(status="found")), 0)
        self.assertEqual(exit_code(ResolveResult(status="not_found")), 1)
        self.assertEqual(exit_code(ResolveResult(status="ambiguous")), 2)

    def test_sha1_bytes(self):
        self.assertEqual(len(sha1_bytes(b"hello")), 12)


class TestCheckDupes(unittest.TestCase):
    def test_check_dupes_groups(self):
        from kb_distillery.lint.lint import check_dupes, warnings
        rows = {
            "raw/a.pdf": {"sha1": "abc123", "disposition": "digested"},
            "raw/b.pdf": {"sha1": "abc123", "disposition": "queued"},
            "raw/c.pdf": {"sha1": "xyz789", "disposition": "digested"},
        }
        from kb_distillery.lint import lint as lint_mod
        lint_mod.warnings = []
        check_dupes(rows)
        self.assertTrue(any("byte-identical" in w for w in lint_mod.warnings))

    def test_check_dupes_skips_dupe_disposition(self):
        from kb_distillery.lint.lint import check_dupes
        from kb_distillery.lint import lint as lint_mod
        lint_mod.warnings = []
        rows = {
            "raw/a.pdf": {"sha1": "abc123", "disposition": "digested"},
            "raw/b.pdf": {"sha1": "abc123", "disposition": "dupe:raw/a.pdf"},
        }
        check_dupes(rows)
        self.assertFalse(lint_mod.warnings)


class TestScrapGuard(unittest.TestCase):
    def test_scrap_blocked_on_resolve_hit(self):
        from kb_distillery.ingest.resolve import ResolveResult
        fake = ResolveResult(status="found", matches=[{"slug": "test-paper", "raw": "raw/papers/x.pdf"}])
        with patch("kb_distillery.ingest.scrap.resolve_mod.resolve", return_value=fake):
            with self.assertRaises(DuplicateBlocked):
                scrap.scrap("https://arxiv.org/abs/2306.13185", force=False)

    def test_scrap_force_skips_pre_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "sample.pdf")
            with open(src, "wb") as f:
                f.write(b"%PDF-1.4 unique-content-xyz")
            with patch("kb_distillery.ingest.scrap.ROOT", tmp):
                with patch("kb_distillery.ingest.scrap.INBOX", os.path.join(tmp, "raw", "inbox")):
                    with patch("kb_distillery.ingest.scrap.resolve_mod.build_indexes") as bi:
                        bi.return_value = type("I", (), {"by_sha1": {}})()
                        rel = scrap.scrap(src, force=True)
                        self.assertTrue(rel.startswith("raw/inbox/"))


class TestResolveIntegration(unittest.TestCase):
    def test_known_arxiv_in_vault(self):
        result = resolve("2306.13185")
        if result.status == "found":
            self.assertTrue(result.matches[0].get("slug"))
        else:
            self.assertIn(result.status, ("not_found", "ambiguous"))


if __name__ == "__main__":
    unittest.main()
