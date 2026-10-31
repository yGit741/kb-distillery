"""relations: (schema 1.4): lint accepts a well-formed block and flags every malformed or undeclared one."""
import unittest

from kb.lint import lint

CONFIG = {"labels": {}, "symmetric": set(), "types": ["addresses", "contradicts", "extends"], "note_required": {"contradicts"}}


def page(slug, fm_extra="", ptype="idea"):
    layer = "concept" if ptype in ("idea", "question") else "source"
    fm = {"type": ptype, "layer": layer, "depth": "full"} if layer == "source" else {"type": ptype, "layer": layer}
    return slug, ("wiki/%s.md" % slug, fm, f"---\ntype: {ptype}\nlayer: {layer}\n{fm_extra}---\n\n# T\n")


def run(*pairs, config=CONFIG):
    import kb.services.cypher as cy
    old, cy.edge_config = cy.edge_config, lambda cfg=None: config
    old_types, lint.SOURCE_TYPES = lint.SOURCE_TYPES, frozenset({"paper"})   # independent of the active kb's types
    lint.errors.clear()
    try:
        lint.check_relations(dict(pairs))
    finally:
        cy.edge_config = old
        lint.SOURCE_TYPES = old_types
        got = list(lint.errors)
        lint.errors.clear()
    return got


class RelationsLint(unittest.TestCase):
    def test_a_clean_block_passes_and_no_block_costs_nothing(self):
        errs = run(page("a", "relations:\n  - to: b\n    kind: extends\n"), page("b"))
        self.assertEqual(errs, [])
        self.assertEqual(run(page("a"), page("b")), [])

    def test_an_empty_list_states_nothing_even_on_an_easy_source_page(self):
        slug, (rel, fm, text) = page("p", "relations: []\n", ptype="paper")
        fm["depth"] = "easy"
        self.assertEqual(run((slug, (rel, fm, text)), page("b")), [])

    def test_each_rule_has_its_own_message(self):
        cases = {
            "not declared": "relations:\n  - to: b\n    kind: inspired-by\n",
            "missing page": "relations:\n  - to: nowhere\n    kind: extends\n",
            "the page itself": "relations:\n  - to: a\n    kind: extends\n",
            "needs a note": "relations:\n  - to: b\n    kind: contradicts\n",
            "stated twice": "relations:\n  - to: b\n    kind: extends\n  - to: b\n    kind: extends\n",
            "must be a list": "relations:\n  - just-a-string\n",
        }
        for needle, block in cases.items():
            errs = run(page("a", block), page("b"))
            self.assertTrue(any(needle in e for e in errs), (needle, errs))

    def test_invalid_yaml_is_an_error(self):
        errs = run(page("a", "relations:\n  - to: [b\n    kind: extends\n"), page("b"))
        self.assertTrue(any("not valid YAML" in e for e in errs), errs)

    def test_a_source_page_needs_depth_full_or_deep(self):
        slug, (rel, fm, text) = page("p", "relations:\n  - to: b\n    kind: extends\n", ptype="paper")
        self.assertEqual(run((slug, (rel, fm, text)), page("b")), [])
        errs = run((slug, (rel, {**fm, "depth": "easy"}, text)), page("b"))
        self.assertTrue(any("needs depth full or deep" in e for e in errs), errs)

    def test_a_kb_that_declares_no_types_accepts_no_relation(self):
        errs = run(page("a", "relations:\n  - to: b\n    kind: extends\n"), page("b"), config={**CONFIG, "types": []})
        self.assertTrue(any("not declared" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
