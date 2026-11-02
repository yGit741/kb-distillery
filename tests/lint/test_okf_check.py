#!/usr/bin/env python3
"""okf-check: OKF v0.2 gaps per rule; any finding fails the run (the blocking commit gate)."""
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from kb_distillery.lint import okf_check


class OkfCheck(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-okf-")
        os.makedirs(os.path.join(self.root, "wiki"))
        os.makedirs(os.path.join(self.root, "raw"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def page(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def rules(self, rel):
        findings, _ = okf_check.check(self.root)
        return sorted(rule for rule, _ in findings.get(rel, []))

    def test_clean_page_has_no_findings(self):
        self.page("wiki/b.md", "---\ntype: idea\n---\n\n# Beta\n")
        self.page("wiki/a.md", "---\ntype: idea\nstatus: stable\ncreated: 2026-10-12T09:00:00+00:00\n"
                  "sources:\n  - resource: /wiki/b.md\n---\n\nSee [B](/wiki/b.md#beta).\n")
        self.assertEqual(okf_check.check(self.root)[0], {})

    def test_frontmatter_rules(self):
        self.page("wiki/a.md", "---\nstatus: digested\ncreated: 2026-10-12\nsources:\n  - title: x\n---\n\nbody\n")
        self.assertEqual(self.rules("wiki/a.md"), ["sources", "status", "timestamp", "type"])

    def test_no_frontmatter_is_a_type_finding(self):
        self.page("wiki/a.md", "just text\n")
        self.assertEqual(self.rules("wiki/a.md"), ["type"])

    def test_body_rules(self):
        self.page("wiki/b.md", "---\ntype: idea\n---\n\n# Beta\n")
        self.page("wiki/a.md", "---\ntype: idea\n---\n\n[[b]] `[[in code]]` [gone](/wiki/nope.md) "
                  "[bad](/wiki/b.md#nope) [raw](/raw/x.pdf) [web](https://example.com)\n")
        self.assertEqual(self.rules("wiki/a.md"), ["boundary", "link", "link", "wikilink"])

    def test_reserved_pages_need_no_type_and_are_not_pages(self):
        self.page("wiki/index.md", "# Index\n")
        self.page("wiki/log.md", "# Log\n\n## 2026-10-12\n- ingest\n")
        self.page("wiki/a.md", "---\ntype: idea\n---\n\nx\n")
        self.assertEqual(okf_check.check(self.root), ({}, 1))

    def test_old_log_entries_may_quote_wikilinks_but_links_are_still_checked(self):
        self.page("wiki/log.md", "# Log\n\n## 2026-10-12\n- see [[index]] and [[gone]]\n")
        self.assertEqual(okf_check.check(self.root)[0], {})
        self.page("wiki/log.md", "# Log\n\n- [gone](nope.md)\n")
        self.assertEqual(self.rules("wiki/log.md"), ["link"])
        self.page("wiki/index.md", "[[x]] [gone](nope.md)\n")
        self.assertEqual(self.rules("wiki/index.md"), ["link", "wikilink"])

    def test_only_the_wiki_bundle_is_checked(self):
        self.page("CLAUDE.md", "no frontmatter\n")
        self.page("copilot/x.md", "no frontmatter\n")
        self.assertEqual(okf_check.check(self.root), ({}, 0))

    def test_math_is_not_a_link(self):
        self.page("wiki/a.md", "---\ntype: idea\n---\n\nWe have $h[P](x)=g[Q](t)$ and\n\n$$f[P](x)$$\n")
        self.assertEqual(okf_check.check(self.root)[0], {})

    def test_unreadable_and_odd_pages_do_not_crash(self):
        with open(os.path.join(self.root, "wiki", "bin.md"), "wb") as f:
            f.write(b"\xff\xfe\x00bad")
        self.page("wiki/s.md", "---\ntype: idea\nsources: 5\n---\n\nx\n")
        self.assertEqual(self.rules("wiki/bin.md"), ["read"])
        self.assertEqual(self.rules("wiki/s.md"), ["sources"])

    def test_main_blocks_on_a_finding_and_names_file_and_rule(self):
        self.page("wiki/a.md", "---\ntype: idea\n---\n\n[[x]]\n")
        out = io.StringIO()
        with mock.patch("kb_distillery.paths.vault_root", return_value=self.root), contextlib.redirect_stdout(out):
            self.assertEqual(okf_check.main([]), 1)
        self.assertIn("ERROR okf-check: wiki/a.md: wikilink: [[x]]", out.getvalue())

    def test_main_passes_a_clean_bundle_and_blocks_when_it_cannot_run(self):
        self.page("wiki/a.md", "---\ntype: idea\n---\n\nx\n")
        with mock.patch("kb_distillery.paths.vault_root", return_value=self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(okf_check.main([]), 0)
            with mock.patch.object(okf_check, "check", side_effect=RuntimeError("boom")):
                self.assertEqual(okf_check.main([]), 1)

    def test_ship_runs_okf_check_as_a_gate(self):
        from kb_distillery.git import ship
        self.assertIn("okf-check", [name for name, _ in ship.GATES])
        self.assertEqual(ship.okf_command(self.root)[-2:], ["-m", "kb_distillery.lint.okf_check"])
        os.makedirs(os.path.join(self.root, "examples", "demo"))
        self.assertEqual(ship.okf_command(self.root)[-3:], ["kb_distillery.lint.okf_check", "--kb", os.path.join(self.root, "examples", "demo")])

    def test_ops_commit_gate_blocks_on_okf_findings(self):
        from kb_distillery.ops import core
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        bad = mock.Mock(returncode=1, stdout="ERROR okf-check: wiki/a.md: type: no parseable non-empty `type`\n"
                        "okf-check: 1 pages, 1 findings (1 type)\n", stderr="")
        with mock.patch.object(core.subprocess, "run", side_effect=[ok, bad]) as run:
            with self.assertRaises(core.OpsError) as cm:
                core.run_lint(self.root)
        self.assertIn("kb_distillery.lint.okf_check", run.call_args_list[1].args[0])
        self.assertIn("wiki/a.md: type", str(cm.exception))
        with mock.patch.object(core.subprocess, "run", side_effect=[ok, ok]):
            core.run_lint(self.root)


if __name__ == "__main__":
    unittest.main()
