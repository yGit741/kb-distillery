#!/usr/bin/env python3
"""Tests for backend/src/kb/report/ — the generic report blocks, their renderers and the text sanitizers."""
import json
import os
import sys
import unittest

from kb.paths import vault_root
ROOT = vault_root()

from kb.report import model as m
from kb.report import render_html, render_text, sanitize

WRANGLER = ("wrangler deploy exited 1: tion issues\n\nPlease check your network connection and try again.\n\n\n"
            "\x1b[31m✘ \x1b[41;31m[\x1b[41;97mERROR\x1b[41;31m]\x1b[0m \x1b[1mfetch failed\x1b[0m\n\n\n"
            "🪵  Logs were written to \"/Users/me/Library/Preferences/.wrangler/logs/w.log\"\n\n"
            " ⛅️ wrangler 4.151.3 (update available 4.152.0)\n───────────────\n\n"
            "If you think this is a bug then please create an issue at https://github.com/x\n"
            "Note that there is a newer version of Wrangler available (4.152.0).")


def sample_doc():
    return m.Doc("kb · nightly report", "warn", "2 to tidy", [
        m.Section("", [m.Banner("warn", "2 to tidy", "kb-0.1.2 · pushed"),
                       m.Stats([m.Stat("Open PRs", "1"), m.Stat("Threads", "3", "warn", "1 stale")])]),
        m.Section("Needs you", [m.Findings([m.Item("error", "deploy-failed", "fetch <failed>", "pixi run share -- deploy-main",
                                                   more="long\noutput")])], id="needs"),
        m.Section("Open threads", [m.Cards([m.Card("PR #4 feat(x): y", "ok", "active", [["age", "2h"]], ["note"],
                                                   "cd .claude/worktrees/x && pixi run ship -- merge   # say \"merge\"",
                                                   "https://github.com/o/r/pull/4", "pr:4")])],
                  note="0 stale", id="threads"),
        m.Section("Last 24 hours", [m.Table(["Step", "Op", "What"], [["kb-0.1.2", "digest", "paper-x"]]),
                                    m.Text("1 step", muted=True), m.Code("line 1\nline 2", "log")], id="recent"),
    ], ["run Fri 23 Oct"], "Fri 23 Oct 22:00", [["Ops dashboard", "http://127.0.0.1:8765/ops"]])


class Sanitize(unittest.TestCase):
    def test_strip_ansi_including_codes_whose_escape_was_lost(self):
        self.assertEqual(sanitize.strip_ansi("\x1b[31mred\x1b[0m [32mgreen[0m"), "red green")

    def test_summarize_wrangler_error(self):
        self.assertEqual(sanitize.summarize_error(WRANGLER), "wrangler deploy exited 1: fetch failed")

    def test_summarize_plain_one_liner_is_kept(self):
        self.assertEqual(sanitize.summarize_error("lint failed — nothing committed"), "lint failed — nothing committed")
        self.assertEqual(sanitize.summarize_error(""), "")

    def test_clean_block_drops_noise_and_shortens_paths(self):
        out = sanitize.clean_block(WRANGLER + "\n/vault/x/.claude/worktrees/a/file.py", root="/vault/x")
        self.assertNotIn("\x1b", out)
        self.assertNotIn("update available", out)
        self.assertNotIn("Logs were written", out)
        self.assertIn(".claude/worktrees/a/file.py", out)
        self.assertNotIn("/vault/x", out)

    def test_short_path(self):
        self.assertEqual(sanitize.short_path("at /v/k/.claude/worktrees/a: dirty", "/v/k", home="/h"),
                         "at .claude/worktrees/a: dirty")
        self.assertEqual(sanitize.short_path("see /h/Library/Logs/x.log", "/v/k", home="/h"), "see ~/Library/Logs/x.log")

    def test_truncate(self):
        self.assertEqual(sanitize.truncate("abcdef", 4), "abc…")
        self.assertEqual(sanitize.truncate("abc", 4), "abc")


class Model(unittest.TestCase):
    def test_worst(self):
        self.assertEqual(m.worst("ok", "warn", "error"), "error")
        self.assertEqual(m.worst("ok", "warn"), "warn")
        self.assertEqual(m.worst(), "ok")

    def test_round_trip_through_json(self):
        doc = sample_doc()
        again = m.Doc.from_dict(json.loads(json.dumps(doc.as_dict())))
        self.assertEqual(again, doc)


class Render(unittest.TestCase):
    def test_html_is_email_safe_and_escaped(self):
        out = render_html.render(sample_doc())
        self.assertTrue(out.startswith("<!doctype html>"))
        self.assertNotIn("<style", out)                       # mail clients drop style blocks
        self.assertNotIn("<script", out)
        self.assertIn("fetch &lt;failed&gt;", out)
        self.assertIn('href="https://github.com/o/r/pull/4"', out)
        self.assertIn("$ cd .claude/worktrees/x &amp;&amp; pixi run ship -- merge", out)
        self.assertIn("say &quot;merge&quot;", out)              # the "# …" comment becomes a muted hint
        self.assertIn("2 to tidy", out)
        self.assertNotIn("long\noutput", out)                 # `more` stays out of the mail

    def test_text_render(self):
        out = render_text.render(sample_doc())
        self.assertTrue(out.startswith("KB · NIGHTLY REPORT"))
        self.assertIn("! 2 to tidy", out)
        self.assertIn("NEEDS YOU", out)
        self.assertIn("✗ deploy-failed: fetch <failed>", out)
        self.assertIn("→ cd .claude/worktrees/x && pixi run ship -- merge", out)
        self.assertIn('(say "merge")', out)
        self.assertIn("kb-0.1.2  digest  paper-x", out)
        self.assertIn("Ops dashboard: http://127.0.0.1:8765/ops", out)

    def test_every_block_kind_renders_in_both(self):
        for kind in m.BLOCK_TYPES:
            self.assertIn(kind, render_html.RENDER)
            self.assertIn(kind, render_text.RENDER)

    def test_empty_lists_render_their_empty_text(self):
        doc = m.Doc("t", "ok", "h", [m.Section("S", [m.Cards([], empty="no threads"), m.Findings([], empty="all good")])])
        self.assertIn("no threads", render_html.render(doc))
        self.assertIn("all good", render_text.render(doc))


if __name__ == "__main__":
    unittest.main()
