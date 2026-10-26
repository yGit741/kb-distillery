import base64
import json
import unittest
from unittest import mock

from kb.share import show

SCRIPT = {"title": "Legend — new", "steps": [{"go": "/graph?view=map", "target": "#a", "title": "T", "body": "b",
                                              "marks": [{"target": "#b", "kind": "new"}], "do": [{"click": "#a"}]}]}


class ShowTest(unittest.TestCase):
    def test_encode_is_base64url_json_without_padding(self):
        code = show.encode(SCRIPT)
        self.assertNotIn("=", code)
        self.assertEqual(json.loads(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4))), SCRIPT)

    def test_links_start_where_the_first_step_is(self):
        with mock.patch.object(show, "deployed_url", return_value="https://kb.example.dev/"):
            ls = show.links(SCRIPT)
        self.assertTrue(ls["local"].startswith("http://127.0.0.1:8765/app/graph?view=map&show="))
        self.assertTrue(ls["deployed"].startswith("https://kb.example.dev/graph?view=map&show="))

    def test_check_names_what_would_fail_quietly(self):
        self.assertEqual(show.check(SCRIPT), [])
        bad = {"title": "", "steps": [{"title": "t", "body": "", "go": "graph", "kind": "red", "do": [{"tap": "#a"}]}]}
        errs = " | ".join(show.check(bad))
        for part in ("title: required", "body required", "go must be", "kind 'red'", "'tap'"):
            self.assertIn(part, errs)
        # malformed shapes are reported, never a traceback
        self.assertTrue(show.check({"title": "t", "steps": ["x"]}))
        self.assertTrue(show.check({"title": "t", "steps": [{"go": "/", "title": "a", "body": "b", "marks": ["#a"], "do": ["click"]}]}))
        self.assertTrue(show.check([]))


if __name__ == "__main__":
    unittest.main()
