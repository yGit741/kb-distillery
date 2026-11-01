import os
import sys
import unittest

from kb_distillery.core.mathnorm import normalize_math, has_legacy_math, protected_spans


class TestMathNorm(unittest.TestCase):
    def test_inline_paren(self):
        out, stats = normalize_math(r"the value \(ax=b\) holds")
        self.assertEqual(out, "the value $ax=b$ holds")
        self.assertEqual(stats["inline"], 1)

    def test_display_bracket(self):
        out, stats = normalize_math(r"\[ x = \frac{b}{a} \]")
        self.assertEqual(out, "$$ x = \\frac{b}{a} $$")
        self.assertEqual(stats["display"], 1)

    def test_gadial_example(self):
        out, _ = normalize_math(r"\(x=\frac{b}{a}\)")
        self.assertEqual(out, r"$x=\frac{b}{a}$")

    def test_latex_dollar(self):
        out, stats = normalize_math(r"$latex ax=b$ inline")
        self.assertEqual(out, "$ax=b$ inline")
        self.assertEqual(stats["inline"], 1)

    def test_equation_env(self):
        out, stats = normalize_math(r"\begin{equation}E=mc^2\end{equation}")
        self.assertEqual(out, "$$E=mc^2$$")
        self.assertEqual(stats["display"], 1)

    def test_fenced_code_untouched(self):
        text = "```\nvar x = \\(1\\);\n```"
        out, stats = normalize_math(text)
        self.assertEqual(out, text)
        self.assertEqual(stats["skipped_fenced"], 1)

    def test_html_js_block_untouched(self):
        text = "```html\n<script>if (\\(x\\)) { y(); }</script>\n```"
        out, _ = normalize_math(text)
        self.assertEqual(out, text)

    def test_inline_code_untouched(self):
        text = "use `\\(x\\)` literally in prose"
        out, _ = normalize_math(text)
        self.assertEqual(out, text)

    def test_currency_untouched(self):
        text = "it costs $100 total, not $200"
        out, _ = normalize_math(text)
        self.assertEqual(out, text)

    def test_already_dollar_untouched(self):
        text = "already $ax=b$ and $$x=y$$"
        out, _ = normalize_math(text)
        self.assertEqual(out, text)

    def test_escaped_backslash_untouched(self):
        text = r"a literal \\(not math\\) stays"
        out, _ = normalize_math(text)
        self.assertEqual(out, text)

    def test_idempotent(self):
        text = r"mix \(a\) and \[b\] and $$c$$ and $d$ and ```\(fenced\)```"
        once, _ = normalize_math(text)
        twice, _ = normalize_math(once)
        self.assertEqual(once, twice)

    def test_idempotent_on_real_style_page(self):
        text = (
            "Extends beyond vanilla GD — min \\(\\ell_2\\) norm interpolator; "
            "\\[ f(x) = \\langle W, \\phi(x) \\rangle \\]\n"
            "and code:\n```python\nprint('\\(literal\\)')\n```\n"
        )
        once, _ = normalize_math(text)
        twice, _ = normalize_math(once)
        self.assertEqual(once, twice)
        self.assertNotIn("\\(", once.split("```")[0])
        self.assertIn("\\(literal\\)", once)  # inside fence, untouched

    def test_has_legacy_math_true(self):
        self.assertTrue(has_legacy_math(r"see \(x\) here"))

    def test_has_legacy_math_false_when_fenced(self):
        self.assertFalse(has_legacy_math("```\n\\(x\\)\n```"))

    def test_has_legacy_math_false_when_already_dollar(self):
        self.assertFalse(has_legacy_math("$x$ and $$y$$"))

    def test_protected_spans_multiple_fences(self):
        text = "a\n```\nb\n```\nc\n```\nd\n```\ne"
        spans = protected_spans(text)
        self.assertEqual(len(spans), 2)

    def test_unclosed_fence_protects_to_end(self):
        text = "before\n```\nunclosed \\(x\\) forever"
        out, _ = normalize_math(text)
        self.assertEqual(out, text)


if __name__ == "__main__":
    unittest.main()
