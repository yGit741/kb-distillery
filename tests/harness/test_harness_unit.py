"""Fast unit tests for the harness building blocks. The slow end-to-end run is `pixi run harness`."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from . import fixture_vault
from . import vault_invariants as inv


def make_vault(pages, corpus=""):
    root = Path(tempfile.mkdtemp(prefix="kb-unit-"))
    (root / "wiki").mkdir()
    (root / "meta").mkdir()
    for slug, text in pages.items():
        (root / "wiki" / f"{slug}.md").write_text(text, encoding="utf-8")
    (root / "meta" / "corpus.tsv").write_text(
        "# h\n# h\npath\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n" + corpus, encoding="utf-8")
    (root / "meta" / "coherence-warnings.tsv").write_text("id\tscore\tkind\tslugs\tsummary\tstatus\nx\t1\tinternal\ta\ts\topen\n",
                                                           encoding="utf-8")
    return root


PAGES = {
    "paper-a": "---\ntype: paper\nlayer: source\ndepth: full\nraw: raw/printed-docs/2020-a.pdf\n---\n\n# A\n\nSee [[idea-b]] and [[missing]] and `[[code]]`.\n",
    "idea-b": "---\ntype: idea\nlayer: concept\n---\n\n# B\n\n[[paper-a]]\n",
    "theme-x": "---\ntype: topic\nlayer: concept\n---\n\n# X\n",
    "course-c": "---\ntype: course\nlayer: collection\nshort: c\n---\n\n# C\n\n## Contents\n\n| 1 | L | `raw/presentations/c-1.pdf` | — | |\n",
}


class InvariantsTest(unittest.TestCase):
    def test_frontmatter_body_split_is_exact(self):
        fm, body = inv.parse_frontmatter("---\ntype: paper\n---\n\n# T\n")
        self.assertEqual(fm["type"], "paper")
        self.assertEqual(body, "\n# T\n")

    def test_counts(self):
        root = make_vault(PAGES, "raw/presentations/c-1.pdf\tabc\tpresentations\tqueued\t\tcourse-c\t\n")
        c = inv.structure_counts(root)
        self.assertEqual(c["pages_total"], 4)
        self.assertEqual(c["pages_by_type"]["source/paper"], 1)
        self.assertEqual(c["pages_by_type"]["concept/topic"], 1)
        self.assertEqual(c["pages_by_layer"], {"collection": 1, "concept": 2, "source": 1})
        self.assertEqual(c["sources_by_type_depth"], {"paper:full": 1})
        self.assertEqual(c["dangling_links"], 1)            # [[missing]]; the one in code is ignored
        self.assertEqual(c["links_total"], 2)
        self.assertEqual(c["orphan_pages"], 2)              # theme-x and course-c have no inbound link
        self.assertEqual(c["coherence_open"], 1)
        self.assertEqual(c["collection_tables"], 1)
        self.assertEqual(c["collection_tables_inconsistent"], 0)
        self.assertEqual(c["raws_unresolvable"], 1)

    def test_collection_inconsistency_detected(self):
        c = inv.structure_counts(make_vault(PAGES, ""))
        self.assertEqual(c["collection_tables_inconsistent_slugs"], ["course-c"])

    def test_body_hash_ignores_front_matter(self):
        a = inv.structure_counts(make_vault(PAGES))["page_bodies_sha256"]
        migrated = dict(PAGES, **{"paper-a": PAGES["paper-a"].replace("type: paper\nlayer: source\ndepth: full", "type: source\nkind: paper\ndepth: full")})
        b = inv.structure_counts(make_vault(migrated))["page_bodies_sha256"]
        self.assertEqual(a, b)
        c = inv.structure_counts(make_vault(dict(PAGES, **{"idea-b": PAGES["idea-b"] + "x\n"})))["page_bodies_sha256"]
        self.assertNotEqual(a["idea-b"], c["idea-b"])

    def test_compare(self):
        base = inv.structure_counts(make_vault(PAGES))
        lines, failed = inv.compare(base, base)
        self.assertEqual((lines, failed), ([], False))
        worse = json.loads(json.dumps(base))
        worse["dangling_links"] += 1
        self.assertTrue(inv.compare(base, worse)[1])
        better = json.loads(json.dumps(base))
        better["dangling_links"] -= 1
        self.assertFalse(inv.compare(base, better)[1])
        fewer = json.loads(json.dumps(base))
        fewer["pages_total"] -= 1
        self.assertTrue(inv.compare(base, fewer)[1])
        body = json.loads(json.dumps(base))
        body["page_bodies_sha256"]["idea-b"] = "0" * 64
        lines, failed = inv.compare(base, body)
        self.assertTrue(failed)
        self.assertIn("BODY CHANGED idea-b", lines)
        dropped = json.loads(json.dumps(base))
        del dropped["pages_by_type"]["source/paper"]
        self.assertTrue(inv.compare(base, dropped)[1])


class FixtureVaultTest(unittest.TestCase):
    def test_seed_has_all_topics(self):
        pages = fixture_vault.seed_pages()
        for t in fixture_vault.TOPICS:
            self.assertIn(f"theme-{t}", pages)
            self.assertIn("layer: concept", pages[f"theme-{t}"])
            self.assertTrue(pages[f"theme-{t}"].rstrip().endswith("-->"))

    def test_inputs_one_per_kind(self):
        d = Path(tempfile.mkdtemp(prefix="kb-unit-in-"))
        made = fixture_vault.build_inputs(d)
        self.assertEqual(set(made), set(fixture_vault.CASES))
        import fitz
        self.assertGreaterEqual(fitz.open(made["collection-book"]).page_count, 60)
        self.assertGreater(len(fitz.open(made["source-paper-local"])[0].get_text()), 200)


if __name__ == "__main__":
    unittest.main()
