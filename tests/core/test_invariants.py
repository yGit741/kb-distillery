#!/usr/bin/env python3
"""src/kb_distillery/ops/invariants.py: identical snapshots compare clean; each kind of damage is caught.

Mutation tests on a tiny temp vault (lint is skipped: its own suite covers it): a body edit, a raw
byte flip, a corpus sha drift and a renamed front-matter field each fail `compare`; the mapped
changes of a spec map (type rename + layer line, field and value renames, disposition) pass.
"""
import os
import shutil
import sys
import tempfile
import unittest

from kb_distillery.ops import invariants as inv

PAPER = """---
type: paper
status: digested
digestion-status: catalog
raw: raw/printed-docs/2024-x.pdf
---

# X

[[tensor-rank]]
"""
CONCEPT = """---
type: concept
status: seed
---

# Tensor rank

[[paper-2024-x]]

## My notes

mine
"""
SPEC = {"types": {"paper": {"layer": "source", "type": "paper"},
                  "concept": {"layer": "concept", "type": "idea"}},
        "rename_fields": {"digestion-status": "depth"},
        "values": {"depth": {"catalog": "listed"}},
        "dispositions": {"digested": "source"}}


class InvariantsTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-inv-")
        self.addCleanup(shutil.rmtree, self.root, True)
        for d in ("wiki", "meta", "raw/printed-docs"):
            os.makedirs(os.path.join(self.root, d))
        self.w("wiki/paper-2024-x.md", PAPER)
        self.w("wiki/tensor-rank.md", CONCEPT)
        with open(os.path.join(self.root, "raw/printed-docs/2024-x.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 tiny")
        from kb_distillery.lint import lint
        old, lint.ROOT = lint.ROOT, self.root
        sha = lint.sha1("raw/printed-docs/2024-x.pdf")
        lint.ROOT = old
        self.w("meta/corpus.tsv", "path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n"
               f"raw/printed-docs/2024-x.pdf\t{sha}\tprinted-docs\tdigested\tpaper-2024-x\t\t\n")
        self.before = inv.snapshot(self.root, lint=False)

    def w(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def r(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def problems(self, spec=None):
        return inv.compare(self.before, inv.snapshot(self.root, lint=False), spec, out=lambda *_: None)

    def test_two_snapshots_identical(self):
        self.assertEqual(self.before, inv.snapshot(self.root, lint=False))
        self.assertEqual(self.problems(), [])

    def test_body_edit_fails(self):
        self.w("wiki/tensor-rank.md", CONCEPT.replace("mine", "theirs"))
        self.assertTrue(any("body changed: tensor-rank" in p for p in self.problems()))

    def test_raw_byte_flip_fails(self):
        with open(os.path.join(self.root, "raw/printed-docs/2024-x.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 tinY")
        probs = self.problems()
        self.assertTrue(any(p.startswith("raw/ changed") for p in probs), probs)
        self.assertTrue(any("sha_mismatch" in p for p in probs), probs)

    def test_corpus_sha_drift_fails(self):
        text = self.r("meta/corpus.tsv")
        row = text.splitlines()[1].split("\t")
        row[1] = "000000000000"
        self.w("meta/corpus.tsv", text.splitlines()[0] + "\n" + "\t".join(row) + "\n")
        self.assertTrue(any("corpus row changed" in p for p in self.problems()))

    def test_renamed_field_fails(self):
        self.w("wiki/paper-2024-x.md", PAPER.replace("digestion-status:", "depth:"))
        self.assertTrue(any("front matter of paper-2024-x" in p for p in self.problems()))

    def test_mapped_change_passes_only_with_map(self):
        self.w("wiki/paper-2024-x.md", PAPER.replace("type: paper\n", "type: paper\nlayer: source\n")
               .replace("digestion-status: catalog", "depth: listed"))
        self.w("wiki/tensor-rank.md", CONCEPT.replace("type: concept\n", "type: idea\nlayer: concept\n"))
        self.w("meta/corpus.tsv", self.r("meta/corpus.tsv").replace("\tdigested\t", "\tsource\t"))
        self.assertTrue(self.problems())                  # without the map: everything differs
        self.assertEqual(self.problems(SPEC), [])

    def test_map_rejects_wrong_layer(self):
        self.w("wiki/tensor-rank.md", CONCEPT.replace("type: concept\n", "type: idea\nlayer: source\n"))
        self.assertTrue(any("front matter of tensor-rank" in p for p in self.problems(SPEC)))

    def test_body_edit_fails_even_with_map(self):
        self.w("wiki/tensor-rank.md", CONCEPT.replace("type: concept\n", "type: idea\nlayer: concept\n")
               .replace("mine", "lost"))
        self.assertTrue(any("body changed: tensor-rank" in p for p in self.problems(SPEC)))

    def test_split_page(self):
        fm, body = inv.split_page(b"---\na: 1\n---\n\nbody\n")
        self.assertEqual((fm, body), (b"---\na: 1\n---\n", b"\nbody\n"))
        self.assertEqual(inv.split_page(b"no fm\n"), (b"", b"no fm\n"))


if __name__ == "__main__":
    unittest.main()
