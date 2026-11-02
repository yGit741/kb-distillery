"""blog-post / ai-chat page types: the blog renderer, catalog detection and the lint rules."""
import os
import shutil
import sys
import tempfile
import unittest

from kb_distillery.paths import vault_root
META = os.path.join(vault_root(), "meta")

from kb_distillery.lint import lint
from kb_distillery.ingest import blog, catalog

POST = """---
title: "פירוק SVD והפירוק הפולארי של מטריצות"
tags: [source/blog-not-exact, subject/linear-algebra]
---

## מבוא

גוף הפוסט עם $A=U\\Sigma V^*$.

```python
A = [[1, 2], [3, 4]]
```
"""


class BlogVault(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for d in ("wiki", "raw/notes/linear-algebra", "meta/chats"):
            os.makedirs(os.path.join(self.root, d))
        self.raw = "raw/notes/linear-algebra/blog-not-exact-svd.md"
        self.write(self.raw, POST)
        self.write("wiki/source-linear-algebra.md", "---\ntype: source\nmaturity: reading\nraw: none\n"
                   "url: x\n---\n# LA\n")
        self._root, lint.ROOT = lint.ROOT, self.root
        lint.errors, lint.warnings = [], []

    def tearDown(self):
        lint.ROOT = self._root
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def errors_for(self, slug):
        lint.errors = []
        lint.check_wiki()
        return [e for e in lint.errors if f"/{slug}.md" in e]


class RenderTests(BlogVault):
    def test_page_shape(self):
        page = blog.render(self.raw, title_en="SVD and Polar", url="https://gadial.net/p/",
                           summary="A blog post about **SVD**.", key_concepts=["**SVD**: x"],
                           root=self.root)
        self.assertIn("type: blog-post", page)
        self.assertIn('aliases: ["פירוק SVD והפירוק הפולארי של מטריצות"]', page)
        self.assertIn("url: https://gadial.net/p/", page)
        self.assertIn("related: [source-linear-algebra.md]", page)
        self.assertIn("## Blog Post Summary\n\nA blog post about **SVD**.", page)
        self.assertIn("- **SVD**: x", page)
        self.assertIn('<div dir="rtl"><strong>פירוק SVD', page)   # Hebrew title under the English one
        self.assertIn('<div dir="rtl">\n\n## מבוא', page)          # body right-to-left
        self.assertNotIn("## Scope", page)
        self.assertNotIn("## Threads", page)

    def test_stub_without_metadata_falls_back_to_original_title(self):
        page = blog.render(self.raw, root=self.root)
        self.assertIn('title: "פירוק SVD והפירוק הפולארי של מטריצות"', page)
        self.assertNotIn("aliases:", page)

    def test_catalog_detects_tagged_posts_only(self):
        self.assertTrue(catalog._looks_like_blog(os.path.join(self.root, self.raw)))
        self.write("raw/notes/linear-algebra/plain.md", "---\ntitle: x\ntags: [subject/linear-algebra]\n---\nhi")
        self.assertFalse(catalog._looks_like_blog(os.path.join(self.root, "raw/notes/linear-algebra/plain.md")))


class XymatrixTests(unittest.TestCase):
    """KaTeX and MathJax have no xy-pic: the tensor-product post's diagrams rendered as errors."""

    def test_triangle_with_stray_brace(self):
        src = "$$\n\\begin{aligned}\n\\xymatrix{ & E\\ar[dd]^{T}\\\\V\\times W\\ar[ur]^h}\\ar[dr]^{f}\\\\ & U}\n\\end{aligned}\n$$"
        out = blog.fix_math(src)
        self.assertNotIn("xymatrix", out)
        self.assertIn(r"\begin{array}{ccc} &  & E \\  & \nearrow^{h} &  \\ V\times W &  & "
                      r"\Big\downarrow{\scriptstyle T} \\  & \searrow^{f} &  \\  &  & U\end{array}", out)
        self.assertTrue(out.startswith("$$\n") and out.endswith("\n$$"))

    def test_nested_brace_labels_stay_on_the_arrow(self):
        out = blog.fix_math("$$\\xymatrix{ & E_{1}\\ar[dd]^{T_{2}T_{1}}\\\\V\\ar[ur]^{h_{1}}\\\\ & E_{1}}$$")
        self.assertIn(r"\Big\downarrow{\scriptstyle T_{2}T_{1}}", out)
        self.assertIn(r"\nearrow^{h_{1}}", out)
        self.assertIn(r" & E_{1} \\", out)

    def test_horizontal_arrow_uses_labelled_xrightarrow(self):
        out = blog.xymatrix_to_array(r"A\ar[r]^{f} & B}")
        self.assertEqual(out, r"\begin{array}{ccc}A & \xrightarrow{f} & B\end{array}")


class LintTests(BlogVault):
    def test_rendered_page_is_lint_clean(self):
        self.write("wiki/blog-not-exact-svd.md", blog.render(self.raw, title_en="SVD", root=self.root))
        self.assertEqual(self.errors_for("blog-not-exact-svd"), [])

    def test_code_sample_is_not_a_wikilink(self):
        self.write("wiki/blog-not-exact-svd.md", blog.render(self.raw, title_en="SVD", root=self.root))
        lint.warnings = []
        pages = lint.check_wiki()
        lint.check_links(pages)
        self.assertFalse([w for w in lint.warnings if "[[1, 2]" in w])

    def test_type_and_prefix_go_together(self):
        page = blog.render(self.raw, title_en="SVD", root=self.root)
        self.write("wiki/svd-post.md", page)
        self.assertTrue(any("requires a blog- filename prefix" in e for e in self.errors_for("svd-post")))
        self.write("wiki/blog-misc.md", "---\ntype: idea\nlayer: concept\nmaturity: seed\n---\n# x\n")
        self.assertTrue(any("blog- prefix requires type: blog-post" in e for e in self.errors_for("blog-misc")))

    def test_ai_chat_needs_real_title_and_tree(self):
        self.write("raw/notes/linear-algebra/c.md", "x")
        self.write("wiki/chat-x.md", "---\ntype: ai-chat\nmaturity: to-read\ntitle: \"New chat\"\n"
                   "raw: raw/notes/linear-algebra/c.md\nconversation: conv-missing\n---\n# New chat 3\n")
        errs = self.errors_for("chat-x")
        self.assertTrue(any("informative title" in e for e in errs))
        self.assertTrue(any("has no tree" in e for e in errs))


class MathRepairTests(unittest.TestCase):
    def test_prefix_balance_rule(self):
        fix = blog.fix_braces
        self.assertEqual(fix(r"$\cal D}_{U\rho} = U {\cal D}_\rho U^{-1$"),
                         r"${\cal D}_{U\rho} = U {\cal D}_\rho U^{-1}$")
        self.assertEqual(fix(r"a $x^{2}$ b $\{x\}$"), r"a $x^{2}$ b $\{x\}$")      # balanced: untouched
        self.assertEqual(fix(r"$\sqrt {\log n$"), r"$\sqrt {\log n$")               # left open: not guessed
        self.assertEqual(fix("$$\n}x{\n$$"), "$$\n}x{\n$$")                          # display blocks untouched

    def test_leftovers_are_reported(self):
        self.assertEqual([f for f, _ in blog.unbalanced_formulas(r"ok $a{b}$ and $\sqrt {\log n$ here")],
                         [r"$\sqrt {\log n$"])

    def test_fix_math_does_it_too(self):
        self.assertEqual(blog.fix_math(r"$\cal D}_x U^{-1$"), r"${\cal D}_x U^{-1}$")


if __name__ == "__main__":
    unittest.main()
