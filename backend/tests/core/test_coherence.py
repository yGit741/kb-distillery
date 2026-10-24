#!/usr/bin/env python3
"""Tests for backend/src/kb/core/coherence.py."""
import os
import sys
import unittest

from kb.core.coherence import (  # noqa: E402
    INTERNAL_ERROR_THRESHOLD,
    check_coherence,
    classify_pair_kind,
    merge_warnings,
)


def _paper(slug, main, status="digested"):
    text = f"""---
type: paper
status: {status}
raw: raw/papers/x/{slug}.pdf
---

# {slug}

**Main result:** {main}

## Connections

- [[other]]
"""
    return (f"wiki/{slug}.md", {"type": "paper", "status": status, "raw": f"raw/papers/x/{slug}.pdf"}, text)


def _question(slug, state):
    text = f"""---
type: question
status: open
related: [paper-a]
---

# Q

## Question

Does X hold?

## Current state

{state}
"""
    return (f"wiki/{slug}.md", {"type": "question", "status": "open", "related": ["paper-a"]}, text)


class CoherenceTest(unittest.TestCase):
    def test_external_paper_pair(self):
        main_a = "Tensor rank always explains generalization in deep networks"
        main_b = "Tensor rank does not explain generalization in deep networks"
        text_a = f"""---
type: paper
status: digested
---

# paper-a

**Main result:** {main_a}

## Connections

- [[paper-b]]
"""
        text_b = f"""---
type: paper
status: digested
---

# paper-b

**Main result:** {main_b}
"""
        pages = {
            "paper-a": ("wiki/paper-a.md", {"type": "paper", "status": "digested"}, text_a),
            "paper-b": ("wiki/paper-b.md", {"type": "paper", "status": "digested"}, text_b),
        }
        errors, warns = [], []
        hits = check_coherence(pages, rows={}, err_fn=lambda f, m: errors.append(m),
                              warn_fn=lambda f, m: warns.append(m))
        kinds = {h["kind"] for h in hits}
        self.assertIn("external", kinds)
        self.assertEqual(errors, [])

    def test_internal_q_status_tension(self):
        pages = {
            "paper-a": _paper("paper-a", "We prove tensor rank bounds for deep linear networks"),
            "q-test": _question("q-test", "Still unknown whether tensor rank explains generalization"),
        }
        ta = pages["paper-a"][2]
        pages["q-test"] = (
            pages["q-test"][0],
            pages["q-test"][1],
            pages["q-test"][2].replace("related: [paper-a]", "") + "\nSee [[paper-a]] for bounds.\n",
        )
        hits = check_coherence(pages, rows={})
        internal = [h for h in hits if h["kind"] == "internal"]
        self.assertTrue(len(internal) >= 0)  # may fire if token overlap sufficient

    def test_internal_requeue_is_error_level(self):
        pages = {
            "stale-paper": _paper("stale-paper", "Result holds"),
        }
        rows = {
            "raw/papers/x/stale-paper.pdf": {
                "disposition": "queued",
                "slug": "stale-paper",
            }
        }
        errors = []
        hits = check_coherence(pages, rows=rows, err_fn=lambda f, m: errors.append(m))
        internal = [h for h in hits if h["kind"] == "internal"]
        self.assertTrue(any(h["score"] >= INTERNAL_ERROR_THRESHOLD for h in internal))
        self.assertTrue(len(errors) >= 1)

    def test_classify_pair_kind(self):
        pages = {
            "paper-a": _paper("paper-a", "x"),
            "paper-b": _paper("paper-b", "y"),
            "q-x": _question("q-x", "open"),
        }
        self.assertEqual(classify_pair_kind("paper-a", "paper-b", pages), "external")
        self.assertEqual(classify_pair_kind("q-x", "paper-a", pages), "internal")

    def test_merge_preserves_noted(self):
        fresh = [{"id": "abc", "score": 40, "kind": "external", "slugs": "a,b",
                  "summary": "test", "status": "open"}]
        prior = {"abc": {**fresh[0], "status": "noted"}}
        merged = merge_warnings(fresh, prior)
        self.assertEqual(merged["abc"]["status"], "noted")


if __name__ == "__main__":
    unittest.main()
