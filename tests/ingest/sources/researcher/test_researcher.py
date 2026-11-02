#!/usr/bin/env python3
"""Tests for src/kb_distillery/ingest/sources/researcher/researcher.py."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.config.paths import vault_root
ROOT = vault_root()

from kb_distillery.ingest.sources.researcher import researcher


AUTHOR_META = {
    "name": "Test Author",
    "affiliations": ["Test University"],
    "homepage": "https://example.edu/~author",
    "url": "https://www.semanticscholar.org/author/999",
    "paperCount": 5,
    "hIndex": 10,
}

PAPERS_RAW = [
    {
        "title": "Star Paper One",
        "year": 2020,
        "citationCount": 500,
        "venue": "NeurIPS",
        "externalIds": {"ArXiv": "2001.00001"},
        "openAccessPdf": {"url": "https://example.edu/star1.pdf"},
        "url": "https://semanticscholar.org/paper/1",
        "paperId": "p1",
    },
    {
        "title": "Silver Paper",
        "year": 2021,
        "citationCount": 80,
        "venue": "ICML",
        "externalIds": {},
        "url": "https://semanticscholar.org/paper/2",
        "paperId": "p2",
    },
    {
        "title": "Below Star",
        "year": 2022,
        "citationCount": 199,
        "venue": "arXiv",
        "externalIds": {"ArXiv": "2201.00002"},
        "url": "https://semanticscholar.org/paper/3",
        "paperId": "p3",
    },
]


class ResearcherLogicTests(unittest.TestCase):
    def test_tier_assignment(self):
        self.assertEqual(researcher._tier_emoji(250)[1], "star")
        self.assertEqual(researcher._tier_emoji(80)[1], "silver")
        self.assertEqual(researcher._tier_emoji(10)[1], "other")

    def test_catalog_selects_star_only_max_rules(self):
        papers_raw = []
        for i in range(12):
            papers_raw.append({
                "title": f"Star Paper {i}",
                "year": 2010 + i,
                "citationCount": 300 + i,
                "venue": "Venue",
                "externalIds": {},
                "paperId": f"s{i}",
            })
        manifest = researcher._build_manifest("Test Author", "999", AUTHOR_META, papers_raw)
        cataloged = [p for p in manifest["papers"] if p.get("catalog")]
        self.assertEqual(len(cataloged), researcher.MAX_CATALOG)
        self.assertTrue(all(p["citation_count"] >= researcher.STAR_MIN_CITES for p in cataloged))
        self.assertNotIn("below", [p["tier"] for p in cataloged])

    def test_build_manifest_excludes_199_from_catalog(self):
        manifest = researcher._build_manifest("Test Author", "999", AUTHOR_META, PAPERS_RAW)
        catalog_slugs = manifest["catalog_slugs"]
        self.assertEqual(len(catalog_slugs), 1)
        star = next(p for p in manifest["papers"] if p["tier"] == "star")
        self.assertIn(star["slug"], catalog_slugs)
        below = next(p for p in manifest["papers"] if p["citation_count"] == 199)
        self.assertFalse(below.get("catalog"))


class ResearcherSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.researcher_root = os.path.join(self.tmp, "meta", ".researcher")
        self.wiki = os.path.join(self.tmp, "wiki")
        os.makedirs(self.wiki)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch.object(researcher, "_ss_get")
    @patch.object(researcher, "_fetch_papers")
    @patch.object(researcher, "_fetch_author")
    @patch.object(researcher, "_resolve_author_id")
    def test_begin_writes_manifest(self, mock_resolve, mock_fetch_author, mock_fetch_papers, mock_ss):
        old_root = researcher.ROOT
        old_rr = researcher.RESEARCHER_ROOT
        researcher.ROOT = self.tmp
        researcher.RESEARCHER_ROOT = self.researcher_root
        try:
            mock_resolve.return_value = ("999", "Test Author")
            mock_fetch_author.return_value = AUTHOR_META
            mock_fetch_papers.return_value = PAPERS_RAW

            slug = researcher.begin("Test Author")
            self.assertEqual(slug, "test-author")
            manifest_path = os.path.join(self.researcher_root, slug, "manifest.json")
            self.assertTrue(os.path.isfile(manifest_path))
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            self.assertEqual(len(manifest["papers"]), 3)
        finally:
            researcher.ROOT = old_root
            researcher.RESEARCHER_ROOT = old_rr

    @patch.object(researcher, "catalog")
    @patch.object(researcher, "scrap")
    @patch.object(researcher, "resolve_mod")
    def test_finalize_writes_person_and_catalogs(self, mock_resolve, mock_scrap, mock_catalog):
        old_root = researcher.ROOT
        old_rr = researcher.RESEARCHER_ROOT
        researcher.ROOT = self.tmp
        researcher.RESEARCHER_ROOT = self.researcher_root
        try:
            slug = "test-author"
            os.makedirs(os.path.join(self.researcher_root, slug))
            manifest = researcher._build_manifest("Test Author", "999", AUTHOR_META, PAPERS_RAW)
            researcher.save_manifest(slug, manifest)
            researcher.save_session(slug, {"slug": slug, "status": "open", "opened_at": researcher._now()})

            mock_resolve.resolve.return_value = type("R", (), {"status": "not_found"})()
            mock_scrap.scrap.return_value = "raw/inbox/fake.pdf"
            mock_catalog.catalog_paper.return_value = (
                "raw/papers/test-author/2020-star-paper-one.pdf",
                "2020-star-paper-one",
            )

            # the arXiv id behind a star paper is verified before download (never the live API here)
            with patch("subprocess.run"), \
                    patch.object(researcher, "verified_arxiv", return_value=("2001.00001", "ok")):
                code = researcher.finalize(slug)
            self.assertEqual(code, 0)
            person_path = os.path.join(self.tmp, "wiki", f"{slug}.md")
            self.assertTrue(os.path.isfile(person_path))
            with open(person_path, encoding="utf-8") as f:
                body = f.read()
            self.assertIn("type: person", body)
            self.assertIn("Star Paper One", body)
            self.assertEqual(mock_catalog.catalog_paper.call_count, 1)
        finally:
            researcher.ROOT = old_root
            researcher.RESEARCHER_ROOT = old_rr

    def test_abort_removes_session(self):
        old_rr = researcher.RESEARCHER_ROOT
        researcher.RESEARCHER_ROOT = self.researcher_root
        try:
            slug = "test-author"
            os.makedirs(os.path.join(self.researcher_root, slug))
            researcher.save_session(slug, {"slug": slug, "status": "open"})
            researcher.save_manifest(slug, {"slug": slug, "papers": []})
            researcher.abort(slug)
            self.assertFalse(os.path.isdir(os.path.join(self.researcher_root, slug)))
        finally:
            researcher.RESEARCHER_ROOT = old_rr


if __name__ == "__main__":
    unittest.main()
