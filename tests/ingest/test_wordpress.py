"""scrap-wordpress: HTML → Markdown, lossless math, figures as `asset:` companions of their clip."""
import os
import shutil
import sys
import tempfile
import unittest

from kb_distillery.paths import vault_root
META = os.path.join(vault_root(), "meta")

from kb_distillery.lint import lint
from kb_distillery.ingest import catalog, htmlmd, wordpress

LATEX = "https://s0.wp.com/latex.php?latex={}&bg=ffffff&fg=000&s=0"
POST = {
    "ID": 7, "date": "2020-07-24T10:00:00+03:00", "modified": "2020-07-25T10:00:00+03:00",
    "title": "Noam Lifshitz: A new inequality &#8212; The proof!", "slug": "noam-lifshitz-a-new-inequality",
    "URL": "https://example.wordpress.com/2020/07/24/noam-lifshitz-a-new-inequality/",
    "categories": {"Analysis": {}, "Combinatorics": {}}, "tags": {}, "word_count": 42,
    "content": (
        '<p>Let <img src="' + LATEX.format("%7Bn%3D1%7D") + '" alt="{n=1}" class="latex"> hold. Then</p>'
        '<p><img src="' + LATEX.format("%5Cdisplaystyle+%5C%7Cf%5C%7C_4%5E4+%5Cle+1") + '" class="latex"></p>'
        '<h2><img src="https://example.wordpress.com/wp-content/uploads/2020/07/bonami.jpg?w=640" alt="Bonami"></h2>'
        '<p><a href="https://example.wordpress.com/wp-content/uploads/2020/07/fig.png">'
        '<img src="https://example.wordpress.com/wp-content/uploads/2020/07/fig.png?w=300" alt="fig"></a></p>'
        '<p><img src="https://example.com/logo.svg" alt="svg"></p>'
        '<iframe src="https://www.youtube.com/embed/eLNEqQjJbao?feature=oembed" allowfullscreen></iframe>'
        '<ul><li>one <b>bold</b></li><li>two</li></ul>'
        '<p>#hashtag text and 3 &lt; 4</p>'),
}


class HtmlMdTests(unittest.TestCase):
    def test_blocks_and_inline(self):
        md = htmlmd.to_markdown("<h2>T &amp; U</h2><p>Hi <b>b</b> <a href='http://x'>l</a><br>next</p>"
                                "<ol><li>a</li><li>b<ul><li>c</li></ul></li></ol><blockquote><p>q</p></blockquote>"
                                "<pre>x_1\n  y</pre><table><tr><th>h</th></tr><tr><td>1|2</td></tr></table>")
        self.assertIn("## T & U", md)
        self.assertIn("Hi **b** [l](http://x)\nnext", md)
        self.assertIn("1. a\n2. b\n\n   - c", md)
        self.assertIn("> q", md)
        self.assertIn("```\nx_1\n  y\n```", md)
        self.assertIn("| h |\n|---|\n| 1\\|2 |", md)

    def test_only_foreign_hashes_are_escaped(self):
        md = htmlmd.to_markdown("<h3>Real</h3><p>#tag</p><p>*star</p>")
        self.assertIn("### Real", md)
        self.assertIn("\\#tag", md)
        self.assertIn("*star", md)


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.stem, self.text, self.images, self.stats = wordpress.to_clip(POST, "example.wordpress.com", "ex")

    def test_math_is_lossless(self):
        self.assertEqual(self.stats["formulas"], 2)
        self.assertIn("Let $n=1$ hold.", self.text)                      # outer braces dropped
        self.assertIn("\n$$\n\\|f\\|_4^4 \\le 1\n$$\n", self.text)         # \displaystyle → block
        self.assertNotIn("latex.php", self.text)

    def test_outer_braces_are_dropped_only_when_they_pair(self):
        """`{\\cal D}_{U\\rho} = U {\\cal D}_\\rho U^{-1}` starts with `{` and ends with `}` with equal
        counts, but its first group closes early: stripping the ends unbalanced the formula."""
        md = wordpress._math_md
        self.assertEqual(md(r"{n=1}"), "$n=1$")
        self.assertEqual(md(r"{{a}+{b}}"), "${a}+{b}$")
        self.assertEqual(md(r"{\cal D}_{U\rho} = U {\cal D}_\rho U^{-1}"),
                         r"${\cal D}_{U\rho} = U {\cal D}_\rho U^{-1}$")
        self.assertEqual(md(r"{a} + {b}"), r"${a} + {b}$")
        self.assertEqual(md(r"\{x\}"), r"$\{x\}$")
        self.assertEqual(md(r"{\{x\}}"), r"$\{x\}$")

    def test_figures_become_local_assets_with_provenance(self):
        self.assertEqual(self.stem, "ex-2020-07-24-noam-lifshitz-a-new-inequality")
        self.assertEqual([n for n, _u in self.images],
                         [f"{self.stem}-01.jpg", f"{self.stem}-02.png"])
        self.assertIn(f'![Bonami](../images/{self.stem}-01.jpg '
                      '"https://example.wordpress.com/wp-content/uploads/2020/07/bonami.jpg")', self.text)
        self.assertNotIn("## ![", self.text)                              # image alone in a heading → figure
        self.assertNotIn("[![fig]", self.text)                            # linked figure → just the figure
        self.assertIn("![svg](https://example.com/logo.svg)", self.text)  # non-image type stays remote
        self.assertEqual(self.stats["images"], 3)

    def test_hebrew_slug_falls_back_to_post_id(self):
        heb = dict(POST, ID=4242, slug="%d7%a9%d7%99%d7%a0%d7%95%d7%99-2015", title="שינוי 2015 – שאלה לנתניהו")
        self.assertEqual(wordpress.clip_stem(heb, "ex"), "ex-2020-07-24-post-4242")
        mixed = dict(POST, slug="%d7%a9%d7%99%d7%a0%d7%95%d7%99-election-day")
        self.assertEqual(wordpress.clip_stem(mixed, "ex"), "ex-2020-07-24-election-day")

    def test_embed_and_frontmatter(self):
        self.assertIn("▶ Embedded video: <https://www.youtube.com/watch?v=eLNEqQjJbao>", self.text)
        self.assertTrue(self.text.startswith('---\ntitle: "Noam Lifshitz: A new inequality — The proof!"\n'))
        self.assertIn("url: https://example.wordpress.com/2020/07/24/noam-lifshitz-a-new-inequality/", self.text)
        self.assertIn('categories: ["Analysis", "Combinatorics"]', self.text)
        self.assertIn("tags: [source/wordpress, blog/example-wordpress-com]", self.text)
        self.assertIn("- one **bold**\n- two", self.text)
        self.assertIn("\\#hashtag text and 3 < 4", self.text)


class ScrapTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "raw", "web-clips"))

    def tearDown(self):
        shutil.rmtree(self.root)

    def _fetch(self, url):
        return {"posts": [POST], "meta": {}}

    def test_writes_clip_and_figures_and_dedups(self):
        fetched = []

        def fetch_image(url, dest):
            fetched.append(url)
            if url.endswith("fig.png"):
                return False                                               # dead host → stays remote
            open(dest, "wb").write(b"jpg")
            return True

        out = wordpress.scrap_wordpress("https://example.wordpress.com/2020/", prefix="ex", root=self.root,
                                        fetch=self._fetch, fetch_image=fetch_image)
        stem = "ex-2020-07-24-noam-lifshitz-a-new-inequality"
        self.assertEqual(out, [f"raw/inbox/{stem}-01.jpg", f"raw/inbox/{stem}.md"])
        text = open(os.path.join(self.root, "raw/inbox", f"{stem}.md"), encoding="utf-8").read()
        self.assertIn(f"](../images/{stem}-01.jpg ", text)
        self.assertIn("![fig](https://example.wordpress.com/wp-content/uploads/2020/07/fig.png)", text)
        self.assertEqual(fetched, ["https://example.wordpress.com/wp-content/uploads/2020/07/bonami.jpg",
                                   "https://example.wordpress.com/wp-content/uploads/2020/07/fig.png"])
        # a second pull skips the post already in the inbox; --force re-pulls it
        self.assertEqual(wordpress.scrap_wordpress("example.wordpress.com", prefix="ex", root=self.root,
                                                   fetch=self._fetch, fetch_image=fetch_image), [])
        self.assertEqual(len(wordpress.scrap_wordpress("example.wordpress.com", prefix="ex", root=self.root,
                                                       force=True, fetch=self._fetch, fetch_image=fetch_image)), 2)

    def test_no_images_keeps_remote_links(self):
        wordpress.scrap_wordpress("example.wordpress.com", prefix="ex", root=self.root, images=False,
                                  fetch=self._fetch, fetch_image=lambda u, d: self.fail("downloaded"))
        text = open(os.path.join(self.root, "raw/inbox/ex-2020-07-24-noam-lifshitz-a-new-inequality.md")).read()
        self.assertNotIn("../images/", text)
        self.assertIn("![Bonami](https://example.wordpress.com/wp-content/uploads/2020/07/bonami.jpg)", text)


class AssetTests(unittest.TestCase):
    def test_lint_binds_a_figure_to_its_clip(self):
        on_disk = {"raw/web-clips/ex-2020-07-24-post.md", "raw/images/ex-2020-07-24-post-01.jpg",
                   "raw/images/ex-2020-07-24-post-102.png", "raw/images/screenshot-01.png",
                   "raw/images/ex-2020-07-24-post.png"}
        self.assertEqual(lint.asset_source("raw/images/ex-2020-07-24-post-01.jpg", on_disk),
                         "raw/web-clips/ex-2020-07-24-post.md")
        self.assertEqual(lint.asset_source("raw/images/ex-2020-07-24-post-102.png", on_disk),
                         "raw/web-clips/ex-2020-07-24-post.md")
        self.assertIsNone(lint.asset_source("raw/images/screenshot-01.png", on_disk))   # no such clip
        self.assertIsNone(lint.asset_source("raw/images/ex-2020-07-24-post.png", on_disk))  # no -NN
        self.assertIsNone(lint.asset_source("raw/web-clips/ex-2020-07-24-post.md", on_disk))

    def test_a_tagged_clip_beats_the_chat_sniff(self):
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "raw/inbox"))
            clip = os.path.join(root, "raw/inbox/ex-post.md")
            open(clip, "w", encoding="utf-8").write(
                "---\ntitle: x\ntags: [source/wordpress, blog/ex]\n---\n**You** said **Gemini** is nice.\n")
            chat = os.path.join(root, "raw/inbox/chat.md")
            open(chat, "w", encoding="utf-8").write("**You**\nhi\n**Gemini**\nhello\n")
            old = catalog.ROOT
            catalog.ROOT = root
            try:
                self.assertEqual(catalog.detect_format("raw/inbox/ex-post.md"), "web-clips")
                self.assertEqual(catalog.detect_format("raw/inbox/chat.md"), "llm-chats")
            finally:
                catalog.ROOT = old
        finally:
            shutil.rmtree(root)

    def test_catalog_recognises_a_figure_in_the_inbox(self):
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "raw/inbox"))
            os.makedirs(os.path.join(root, "raw/web-clips"))
            open(os.path.join(root, "raw/inbox/ex-post.md"), "w").close()
            open(os.path.join(root, "raw/web-clips/old-post.md"), "w").close()
            old = catalog.ROOT
            catalog.ROOT = root
            try:
                self.assertEqual(catalog.asset_clip("raw/inbox/ex-post-01.png"), "ex-post")
                self.assertEqual(catalog.asset_clip("raw/inbox/old-post-07.gif"), "old-post")
                self.assertIsNone(catalog.asset_clip("raw/inbox/lonely-01.png"))
                self.assertIsNone(catalog.asset_clip("raw/inbox/ex-post.md"))
            finally:
                catalog.ROOT = old
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()


class TextClipExtractTests(unittest.TestCase):
    def test_markdown_clip_is_read_as_text_not_pdf(self):
        from kb_distillery.ingest import extract
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "clip.md")
            open(p, "w", encoding="utf-8").write("---\ntitle: x\nurl: u\n---\n# T\n\nBody $a^2$.\n")
            self.assertEqual(extract.extract_text(p), "# T\n\nBody $a^2$.\n")
            h = os.path.join(d, "page.html")
            open(h, "w", encoding="utf-8").write("<p>Hi <b>there</b></p>")
            self.assertIn("Hi  there", extract.extract_text(h))
        finally:
            shutil.rmtree(d)
