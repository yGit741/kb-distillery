import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from kb_distillery.publish.site.home import apply_home, load_home, strip_my_notes

PAGE = "# Idea\n\n## One-liner\n\nShared text.\n\n## My notes\n\nprivate thought\n\n- more private\n"


def blob():
    return {
        "graph": {"nodes": [{"id": "a"}, {"id": "b"}]},
        "pages": {"a": {"markdown": PAGE}, "b": {"markdown": "# B\n\nno notes\n"}},
    }


class TestShareHome(unittest.TestCase):
    def test_strip_my_notes_keeps_everything_else(self):
        out = strip_my_notes(PAGE)
        self.assertIn("Shared text.", out)
        self.assertNotIn("private", out)
        self.assertNotIn("My notes", out)
        mid = "# T\n\n## My notes\n\nx\n\n## Later\n\nkept\n"
        self.assertIn("kept", strip_my_notes(mid))
        self.assertNotIn("\nx\n", strip_my_notes(mid))
        self.assertEqual(strip_my_notes("no notes, no newline"), "no notes, no newline")

    def test_public_profile_drops_my_notes_private_keeps_them(self):
        from kb_distillery.publish.site.build import apply_profile

        def data():
            return {"graph": {"nodes": [{"id": "a", "type": "idea"}], "links": [], "concept_links": []},
                    "index": {"pages": [{"id": "a", "type": "idea"}], "links": [], "wanted": []},
                    "pages": {"a": {"card": {"type": "idea"}, "markdown": PAGE}}}

        public = apply_profile(data(), "public")["pages"]["a"]["markdown"]
        self.assertNotIn("private thought", public)
        self.assertIn("Shared text.", public)
        self.assertIn("private thought", apply_profile(data(), "private")["pages"]["a"]["markdown"])

    def test_cards_keep_only_present_pages_and_drop_empty_ones(self):
        home = {"cards": [{"title": "T", "pages": ["a", "gone"], "focus": "gone", "caption": "c"},
                          {"title": "Empty", "pages": ["gone"]}], "tour": "kalai"}
        data = apply_home(blob(), home)
        self.assertEqual(data["home"], {"cards": [{"title": "T", "pages": ["a"], "caption": "c"}], "tour": "kalai"})

    def test_load_home_reads_share_toml(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "share.toml"
            p.write_text('[home]\ntour = "kalai"\n[[home.cards]]\ntitle = "X"\npages = ["a"]\n[[home.cards]]\ntitle = "bad"\n',
                         encoding="utf-8")
            self.assertEqual(load_home(p), {"cards": [{"title": "X", "pages": ["a"]}], "tour": "kalai"})
            self.assertEqual(load_home(Path(d) / "missing.toml"), {"cards": [], "tour": None})


if __name__ == "__main__":
    unittest.main()
