"""backfill._set_url keeps `url:` and `sources:` in step: a lone url is never written to `sources`; other entries stay."""
import os
import tempfile
import unittest

from kb_distillery.vault import frontmatter
from kb_distillery.ingest import backfill


def page(extra=""):
    return f"---\ntype: paper\nlayer: source\nurl: https://old.org/a\n{extra}---\n\n# P\n"


class SetUrl(unittest.TestCase):
    def run_set(self, text, url):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "paper-p.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            backfill._set_url(path, url)
            with open(path, encoding="utf-8") as f:
                return f.read()

    def test_a_lone_url_is_not_written_to_sources(self):
        out = self.run_set(page(), "https://new.org/a")
        fm = frontmatter.parse(out)[0]
        self.assertEqual(fm["url"], "https://new.org/a")
        self.assertNotIn("sources", fm)
        self.assertEqual(frontmatter.resources(fm), ["https://new.org/a"])

    def test_the_old_url_resource_goes_and_nothing_replaces_it(self):
        out = self.run_set(page("sources: [{resource: https://old.org/a}]\n"), "https://new.org/a")
        self.assertNotIn("sources", frontmatter.parse(out)[0])

    def test_other_sources_stay_and_the_new_url_joins_them(self):
        out = self.run_set(page("sources: [{resource: https://old.org/a}, {resource: idea-x.md}]\n"), "https://new.org/a")
        fm = frontmatter.parse(out)[0]
        self.assertEqual(frontmatter.resources(fm), ["https://new.org/a", "idea-x.md"])

    def test_an_emptied_url_leaves_the_other_sources(self):
        out = self.run_set(page("sources: [{resource: idea-x.md}]\n"), "")
        fm = frontmatter.parse(out)[0]
        self.assertEqual(frontmatter.resources(fm), ["idea-x.md"])
        self.assertEqual(fm["url"], "")


if __name__ == "__main__":
    unittest.main()
