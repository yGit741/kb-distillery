import io
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from kb_distillery.git import claims, ship


def _cp(rc=0, out=""):
    return subprocess.CompletedProcess([], rc, out, "")


class OverlapTest(unittest.TestCase):
    def test_dir_prefix_matches_file(self):
        self.assertEqual(claims.overlap(["src/kb_distillery/git"], ["src/kb_distillery/git/ship.py", "README.md"]),
                         ["src/kb_distillery/git/ship.py"])

    def test_reverse_prefix_and_equal(self):
        self.assertEqual(claims.overlap(["web/src/a/b.tsx", "x/y/"], ["web/src", "x/y"]),
                         ["web/src/a/b.tsx", "x/y"])

    def test_no_overlap_on_name_prefix(self):
        self.assertEqual(claims.overlap(["src/kb_distillery/git"], ["src/kb_distillery/gitx/a.py", "frontend"]), [])

    def test_parse_and_body(self):
        self.assertEqual(claims.parse_paths("./a/b/, c/d,a/b"), ["a/b", "c/d"])
        body = ship.pr_body(["feat(x): y"], paths=["a/b", "c/d"])
        self.assertIn("Claims: a/b, c/d", body)
        self.assertEqual(claims.claims_from_body(body), ["a/b", "c/d"])
        self.assertNotIn("Claims:", ship.pr_body(["feat(x): y"]))

    def test_touched_dirs(self):
        self.assertEqual(claims.touched_dirs(["a/b/c.py", "a/b/d.py", "top.md"]), ["a/b", "top.md"])


class WarnTest(unittest.TestCase):
    PRS = ('[{"number": 7, "headRefName": "infra/other", "title": "feat(git): other", '
           '"body": "Claims: src/kb_distillery/git\\n\\n## Summary"},'
           '{"number": 8, "headRefName": "infra/nobody", "title": "fix(app): z", "body": "## Summary"}]')

    def _run(self, mine, gh):
        buf = io.StringIO()
        with mock.patch.object(claims, "_gh", side_effect=gh), \
                mock.patch.object(claims, "worktree_lanes", return_value=[]), redirect_stdout(buf):
            hits = claims.warn(mine, "infra/me", "/tmp")
        return hits, buf.getvalue()

    def test_overlap_block(self):
        def gh(args, root):
            if args[:2] == ["pr", "list"]:
                return _cp(out=self.PRS)
            return _cp(out='{"files": [{"path": "web/src/x.tsx"}]}')
        hits, out = self._run(["src/kb_distillery/git/ship.py"], gh)
        self.assertEqual([h[0]["pr"] for h in hits], [7])
        self.assertIn("OVERLAP", out)
        self.assertIn("PR #7 feat(git): other", out)

    def test_files_fallback(self):
        def gh(args, root):
            if args[:2] == ["pr", "list"]:
                return _cp(out=self.PRS)
            return _cp(out='{"files": [{"path": "web/src/x.tsx"}]}')
        hits, _ = self._run(["web"], gh)
        self.assertEqual([h[0]["pr"] for h in hits], [8])

    def test_no_overlap(self):
        hits, out = self._run(["meta/docs"], lambda a, r: _cp(out=self.PRS if a[:2] == ["pr", "list"] else "{}"))
        self.assertEqual(hits, [])
        self.assertNotIn("OVERLAP", out)

    def test_gh_failure_is_non_fatal(self):
        hits, out = self._run(["backend"], lambda a, r: _cp(rc=1))
        self.assertEqual(hits, [])
        self.assertIn("gh unavailable", out)

    def test_worktree_lane(self):
        buf = io.StringIO()
        lanes = [{"branch": "infra/wt", "path": "/w", "paths": [".claude/skills/infra-pr/SKILL.md"], "claims": []}]
        with mock.patch.object(claims, "_gh", return_value=_cp(rc=1)), \
                mock.patch.object(claims, "worktree_lanes", return_value=lanes), redirect_stdout(buf):
            hits = claims.warn([".claude/skills"], "infra/me", "/tmp")
        self.assertEqual(len(hits), 1)
        self.assertIn("worktree /w", buf.getvalue())

    def test_exception_never_raises(self):
        with mock.patch.object(claims, "find_overlaps", side_effect=RuntimeError("boom")), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(claims.warn(["a"], "infra/me", "/tmp"), [])


if __name__ == "__main__":
    unittest.main()
