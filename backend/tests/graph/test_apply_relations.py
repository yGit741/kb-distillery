"""Applying accepted relation proposals: the page edit (set_relations) and the selection (plan_apply)."""
import unittest

from kb.graph import propose as P
from kb.graph import relations as R

CONFIG = {"labels": {}, "symmetric": {"contradicts", "CONTRADICTS"},
          "types": ["addresses", "contradicts", "extends", "uses"], "note_required": {"contradicts"}}

PAGE = "---\ntype: idea\nlayer: concept\nstatus: seed\n---\n\n# Title\n\nbody\n"


def page(slug, text=PAGE):
    return slug, {"slug": slug, "text": text}


def row(a, b, kind="uses", conf=0.8, note=""):
    return {"from": a, "to": b, "kind": kind, "confidence": conf, "note": note}


class SetRelations(unittest.TestCase):
    def test_a_block_is_added_after_the_last_key_and_reads_back(self):
        out = R.set_relations(PAGE, [{"to": "b", "kind": "uses", "note": ""},
                                     {"to": "c", "kind": "extends", "note": 'says "why"'}])
        self.assertEqual(R.parse_relations(out), [{"to": "b", "kind": "uses", "note": ""},
                                                  {"to": "c", "kind": "extends", "note": 'says "why"'}])
        self.assertTrue(out.endswith("---\n\n# Title\n\nbody\n"))                 # the body is untouched
        self.assertIn("status: seed\nrelations:\n", out)

    def test_an_existing_block_is_replaced_not_duplicated(self):
        once = R.set_relations(PAGE, [{"to": "b", "kind": "uses", "note": ""}])
        twice = R.set_relations(once, R.parse_relations(once) + [{"to": "c", "kind": "extends", "note": ""}])
        self.assertEqual(twice.count("relations:"), 1)
        self.assertEqual([r["to"] for r in R.parse_relations(twice)], ["b", "c"])
        self.assertTrue(twice.endswith("---\n\n# Title\n\nbody\n"))

    def test_a_block_before_another_key_keeps_that_key(self):
        text = "---\ntype: idea\nrelations:\n  - to: b\n    kind: uses\nstatus: seed\n---\n\nbody\n"
        out = R.set_relations(text, R.parse_relations(text) + [{"to": "c", "kind": "extends", "note": ""}])
        self.assertIn("status: seed", out)
        self.assertEqual([r["to"] for r in R.parse_relations(out)], ["b", "c"])

    def test_a_page_without_frontmatter_is_an_error(self):
        with self.assertRaises(ValueError):
            R.set_relations("# no frontmatter\n", [{"to": "b", "kind": "uses", "note": ""}])


class PlanApply(unittest.TestCase):
    def setUp(self):
        self.pages = dict([page("a"), page("b"), page("c")])

    def plan(self, rows, min_conf=0.8, **kw):
        return P.plan_apply(rows, self.pages, CONFIG, min_conf, **kw)

    def test_only_rows_at_or_above_the_confidence_are_taken(self):
        out, _ = self.plan([row("a", "b", conf=0.9), row("a", "c", conf=0.6)])
        self.assertEqual(out, {"a": [{"to": "b", "kind": "uses", "note": ""}]})

    def test_kinds_and_subjects_narrow_the_choice(self):
        rows = [row("a", "b"), row("a", "c", kind="extends"), row("b", "c")]
        self.assertEqual(set(self.plan(rows, kinds={"extends"})[0]), {"a"})
        self.assertEqual(set(self.plan(rows, subjects={"b"})[0]), {"b"})

    def test_what_lint_would_reject_is_skipped_with_the_reason(self):
        out, skipped = self.plan([row("a", "nowhere"), row("a", "a"), row("a", "b", kind="inspired-by"),
                                  row("a", "c", kind="contradicts")])
        self.assertEqual(out, {})
        reasons = " | ".join(why for _, why in skipped)
        for needle in ("missing page", "the page itself", "not declared", "needs a note"):
            self.assertIn(needle, reasons)

    def test_a_relation_the_page_already_states_is_skipped(self):
        self.pages["a"]["text"] = R.set_relations(PAGE, [{"to": "b", "kind": "uses", "note": ""}])
        out, skipped = self.plan([row("a", "b"), row("a", "c")])
        self.assertEqual([r["to"] for r in out["a"]], ["c"])
        self.assertEqual([why for _, why in skipped], ["already stated"])

    def test_a_symmetric_pair_stated_from_the_other_side_is_skipped(self):
        self.pages["b"]["text"] = R.set_relations(PAGE, [{"to": "a", "kind": "contradicts", "note": "x vs y"}])
        out, skipped = self.plan([row("a", "b", kind="contradicts", note="y vs x")])
        self.assertEqual(out, {})
        self.assertEqual([why for _, why in skipped], ["already stated"])

    def test_the_same_proposal_twice_is_one_relation(self):
        out, _ = self.plan([row("a", "b"), row("a", "b")])
        self.assertEqual(len(out["a"]), 1)

    def test_the_limit_caps_pages_and_keeps_the_strongest(self):
        out, _ = self.plan([row("a", "b", conf=0.8), row("b", "c", conf=0.95), row("c", "a", conf=0.9)], limit=2)
        self.assertEqual(set(out), {"b", "c"})


if __name__ == "__main__":
    unittest.main()
