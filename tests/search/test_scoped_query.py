#!/usr/bin/env python3
"""Scoped query: `candidates --scope`, `scope-status`, `explore_raw find --scope`, `citations missing
--scope`, the chat policy / system prompt / direct retrieval inside a scope. A temp vault, no network."""
import pytest

from kb_distillery.core import schema as _schema

if "paper" not in _schema.SOURCE_TYPES:   # this module builds `paper` pages: it needs the explorer's default types
    pytest.skip("needs the default source types (run with KB=yonatan-thesis or a kb that defines `paper`)", allow_module_level=True)

import asyncio
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from kb_distillery.paths import vault_root
HERE = os.path.join(vault_root(), "meta")

from kb_distillery.search import citations
from kb_distillery.search import explore_raw
from kb_distillery.lint import lint
from kb_distillery.search import query
from kb_distillery.core import scopes as sc
from kb_distillery.services import chat_agent
from kb_distillery.services import chat as chat_data

A = "raw/printed-docs/2023-a.pdf"
B = "raw/printed-docs/2023-b.pdf"
C = "raw/web-clips/2023-c-clip.md"
Z = "raw/printed-docs/2023-zeta-tensor.pdf"


def page(typ, status, body, fm=None):
    from kb_distillery.core import schema
    typ = {"concept": "idea", "theme": "topic"}.get(typ, typ)
    lines = ["---", "type: " + typ, "layer: " + schema.LAYER_OF[typ], "status: " + status]
    lines += [k + ": " + str(v) for k, v in (fm or dict()).items()]
    return "\n".join(lines + ["---", "", body]) + "\n"


def paper(slug, raw, links, n):
    fm = dict(year=2023, area="[learning-theory]", raw=raw, url="https://arxiv.org/abs/2301.0000" + str(n))
    fm["depth"] = "full"
    return page("paper", "digested", "# " + slug + "\n\nSee " + " ".join("[[" + l + "]]" for l in links), fm)


TEXTS = dict()
TEXTS["scope-s"] = page("scope", "active", "# Scope S\n\n## Why\n\nBecause.\n\n## Members\n")
TEXTS["paper-a"] = paper("paper-a", A, ["concept-x", "q-y"], 1)
TEXTS["paper-b"] = paper("paper-b", B, ["concept-x"], 2)
TEXTS["paper-z"] = paper("paper-z", Z, ["concept-z"], 3)
TEXTS["concept-x"] = page("concept", "seed", "# concept-x\n")
TEXTS["concept-z"] = page("concept", "seed", "# concept-z\n")
TEXTS["q-y"] = page("question", "open", "# q-y\n")
SUMMARY = dict()
SUMMARY["paper-a"] = "alpha tensor result"
SUMMARY["paper-b"] = "beta tensor result"
SUMMARY["paper-z"] = "zeta tensor rank"
SUMMARY["concept-x"] = "x tensor idea"
SUMMARY["concept-z"] = "z tensor idea"
SUMMARY["q-y"] = "open tensor question"
SUMMARY["scope-s"] = "scope s"
ROWS = [(A, "source", "paper-a", "scope-s"), (B, "source", "paper-b", "scope-s"),
        (C, "queued", "", "scope-s"), (Z, "source", "paper-z", "")]


def build_vault(root):
    os.makedirs(os.path.join(root, "wiki"))
    os.makedirs(os.path.join(root, "meta"))
    for slug, text in TEXTS.items():
        with open(os.path.join(root, "wiki", slug + ".md"), "w") as f:
            f.write(text)
    with open(os.path.join(root, "index.md"), "w") as f:
        f.write("## Papers\n\n| Page | Status | Summary |\n|---|---|---|\n")
        for slug, summ in SUMMARY.items():
            f.write("| [[" + slug + "]] | seed | " + summ + " |\n")
    lines = ["path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes"]
    for path, disp, slug, scope in ROWS:
        lines.append("\t".join([path, "x", path.split("/")[1], disp, slug, "", scope]))
    with open(os.path.join(root, "meta", "corpus.tsv"), "w") as f:
        f.write("\n".join(lines) + "\n")


class VaultCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-scoped-")
        self.addCleanup(shutil.rmtree, self.root, True)
        build_vault(self.root)
        sc._CTX_CACHE.clear()
        patches = [(query, "ROOT", self.root), (query, "WIKI", os.path.join(self.root, "wiki")),
                   (query, "INDEX", os.path.join(self.root, "index.md")),
                   (lint, "ROOT", self.root), (explore_raw, "ROOT", self.root), (citations, "ROOT", self.root)]
        for target, name, value in patches:
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def run_cli(self, fn, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = fn(*args)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()


class ContextTests(VaultCase):
    def test_context_shape(self):
        ctx = sc.scope_context("scope-s", self.root)
        self.assertEqual(ctx["slug"], "scope-s")
        self.assertEqual(ctx["title"], "Scope S")
        self.assertEqual(ctx["pages"], set(["scope-s", "paper-a", "paper-b", "concept-x"]))
        self.assertEqual(ctx["covered"], [A, B])
        self.assertEqual([u["path"] for u in ctx["uncovered"]], [C])
        self.assertEqual(ctx["uncovered"][0]["format"], "web-clips")
        self.assertEqual(ctx["uncovered"][0]["name"], "2023-c-clip.md")
        self.assertAlmostEqual(ctx["coverage"], 2 / 3)
        self.assertEqual(ctx["rows"], sorted([A, B, C]))

    def test_unknown_scope(self):
        with self.assertRaises(sc.ScopeUnknown):
            sc.scope_context("scope-nope", self.root)
        with self.assertRaises(sc.ScopeUnknown):
            sc.scope_context("paper-a", self.root)     # a page, but not a scope

    def test_cache_invalidates_on_change(self):
        self.assertNotIn("paper-z", sc.scope_context("scope-s", self.root)["pages"])
        path = os.path.join(self.root, "meta", "corpus.tsv")
        old = Z + "\tx\tprinted-docs\tsource\tpaper-z\t\t"
        text = open(path).read().replace(old, old + "scope-s")
        open(path, "w").write(text)
        later = os.path.getmtime(path) + 5
        os.utime(path, (later, later))
        self.assertIn("paper-z", sc.scope_context("scope-s", self.root)["pages"])


class QueryCliTests(VaultCase):
    def test_candidates_unscoped_sees_everything(self):
        code, out, _ = self.run_cli(query.cmd_candidates, "tensor", 20)
        self.assertEqual(code, 0)
        self.assertIn("[[paper-z]]", out)
        self.assertIn("[[paper-a]]", out)

    def test_candidates_scoped_restricts(self):
        code, out, _ = self.run_cli(query.cmd_candidates, "tensor", 20, "scope-s")
        self.assertEqual(code, 0)
        self.assertIn("[scope scope-s]", out)
        for slug in ("paper-a", "paper-b", "concept-x"):
            self.assertIn("[[" + slug + "]]", out)
        for slug in ("paper-z", "concept-z"):
            self.assertNotIn("[[" + slug + "]]", out)

    def test_candidates_unknown_scope_exits_2(self):
        code, out, err = self.run_cli(query.cmd_candidates, "tensor", 20, "scope-nope")
        self.assertEqual(code, 2)
        self.assertIn("unknown scope", err)

    def test_main_parses_scope_flag(self):
        code, out, _ = self.run_cli(query.main, ["candidates", "tensor", "--scope", "scope-s"])
        self.assertEqual(code, 0)
        self.assertNotIn("paper-z", out)

    def test_scope_status(self):
        code, out, _ = self.run_cli(query.main, ["scope-status", "scope-s"])
        self.assertEqual(code, 0)
        self.assertIn("SCOPE  scope-s  Scope S", out)
        self.assertIn("Coverage: 2/3 files digested (67%) · 1 undigested", out)
        self.assertIn("[[paper-a]]  alpha tensor result", out)
        self.assertNotIn("[[paper-z]]", out)
        self.assertIn("NOT_YET_DIGESTED  (1)", out)
        self.assertIn("  " + C, out)

    def test_scope_status_unknown_exits_2(self):
        code, _out, err = self.run_cli(query.main, ["scope-status", "scope-nonexistent"])
        self.assertEqual(code, 2)
        self.assertIn("scope-nonexistent", err)


class ExploreTests(VaultCase):
    def test_find_scope(self):
        _c, out, _ = self.run_cli(explore_raw.cmd_find, ["tensor"], 10, False)
        self.assertIn(Z, out)
        code, out, _ = self.run_cli(explore_raw.cmd_find, ["tensor"], 10, False, "scope-s")
        self.assertEqual(code, 0)
        self.assertIn(A, out)
        self.assertNotIn(Z, out)

    def test_find_scope_undigested_row_by_name(self):
        _c, out, _ = self.run_cli(explore_raw.cmd_find, ["clip"], 10, False, "scope-s")
        self.assertIn("UNDIGESTED", out)
        self.assertIn(C, out)

    def test_find_unknown_scope_refused(self):
        code, _out, err = self.run_cli(explore_raw.main, ["find", "tensor", "--scope", "scope-nope"])
        self.assertEqual(code, 2)
        self.assertIn("unknown scope", err)


class CitationsTests(VaultCase):
    def setUp(self):
        super().setUp()

        def node(slug, refs, title=""):
            return dict(slug=slug, title=title or "T-" + str(slug), year=2023, arxiv=None, doi=None,
                        citationCount=0, references=refs, citations=[], fetched_at="x")
        cache = citations.empty_cache()
        cache["papers"] = dict(pa=node("paper-a", ["e1", "e2"]), pb=node("paper-b", ["e1"]),
                               pz=node("paper-z", ["e3"]), e1=node(None, [], "ext-e1"),
                               e2=node(None, [], "ext-e2"), e3=node(None, [], "ext-e3"))
        cache["slugs"] = dict()
        cache["slugs"]["paper-a"] = "pa"
        cache["slugs"]["paper-b"] = "pb"
        cache["slugs"]["paper-z"] = "pz"
        citations.save_cache(cache)

    def test_missing_unscoped_includes_all(self):
        _c, out, _ = self.run_cli(citations.main, ["missing"])
        self.assertIn("ext-e3", out)

    def test_missing_scoped(self):
        _c, out, _ = self.run_cli(citations.main, ["missing", "--scope", "scope-s"])
        self.assertIn("scope scope-s: 2 vault papers", out)
        self.assertIn("ext-e1", out)
        self.assertIn("ext-e2", out)
        self.assertNotIn("ext-e3", out)

    def test_scope_papers_and_unknown(self):
        self.assertEqual(citations.scope_papers("scope-s"), ["paper-a", "paper-b"])
        code, _out, _err = self.run_cli(citations.main, ["missing", "--scope", "scope-nope"])
        self.assertEqual(code, 2)

    def test_fetch_scope_limits_slugs(self):
        with mock.patch.object(citations, "fetch") as f:
            self.run_cli(citations.main, ["fetch", "--scope", "scope-s"])
        f.assert_called_once()
        self.assertEqual(f.call_args[0][0], ["paper-a", "paper-b"])


# ── chat ───────────────────────────────────────────────────────────────────

CROOT = chat_agent.ROOT
CLIP = "raw/web-clips/2023-c-clip.md"
SCOPE = dict(slug="scope-s", title="Scope S", pages=set(["scope-s", "tensor-rank", "paper-a"]),
             covered=["raw/printed-docs/2023-a.pdf"], rows=[CLIP, "raw/printed-docs/2023-a.pdf"],
             uncovered=[dict(path=CLIP, name="2023-c-clip.md", format="web-clips")], coverage=0.5)


def wiki(slug):
    return os.path.join(CROOT, "wiki", slug + ".md")


def fp(path):
    return dict(file_path=path)


class ScopedPolicyTests(unittest.TestCase):
    def d(self, tool, inp, scope=SCOPE):
        return chat_agent.tool_policy(tool, inp, scope)

    def test_read_in_and_out_of_scope(self):
        self.assertTrue(self.d("Read", fp(wiki("tensor-rank"))).allow)
        self.assertTrue(self.d("Read", fp("wiki/paper-a.md")).allow)
        self.assertTrue(self.d("Read", fp("index.md")).allow)
        out = self.d("Read", fp(wiki("theme-info-theory")))
        self.assertFalse(out.allow)
        self.assertIn("scope", out.reason)

    def test_think_closed(self):
        self.assertFalse(self.d("Read", fp("think/ideas.md")).allow)
        self.assertFalse(self.d("Grep", dict(pattern="x", path="think")).allow)
        self.assertTrue(chat_agent.tool_policy("Read", fp("think/ideas.md")).allow)   # unscoped unchanged

    def test_raw_only_scope_rows(self):
        self.assertTrue(self.d("Read", fp(CLIP)).allow)
        self.assertFalse(self.d("Read", fp("raw/web-clips/other.md")).allow)
        self.assertFalse(self.d("Read", fp("raw/printed-docs/2023-a.pdf")).allow)

    def test_wiki_subpath_and_traversal(self):
        self.assertFalse(self.d("Read", fp("wiki/../src/kb_distillery/core/schema.py")).allow)
        self.assertFalse(self.d("Read", fp("wiki/sub/tensor-rank.md")).allow)

    def test_grep_glob_default_to_wiki(self):
        out = self.d("Grep", dict(pattern="tensor"))
        self.assertTrue(out.allow)
        self.assertEqual(out.updated_input["path"], chat_agent.WIKI)
        self.assertTrue(self.d("Glob", dict(pattern="*.md", path="wiki")).allow)

    def test_unscoped_policy_unchanged(self):
        cases = [("Read", fp(wiki("theme-info-theory"))),
                 ("Bash", dict(command="python3 -m kb_distillery.search.query candidates tensor")),
                 ("Bash", dict(command="python3 -m kb_distillery.search.query mocs"))]
        for tool, inp in cases:
            self.assertTrue(chat_agent.tool_policy(tool, inp).allow, inp)
            self.assertTrue(chat_agent.tool_policy(tool, inp, None).allow, inp)

    def bash(self, cmd):
        return self.d("Bash", dict(command=cmd)).allow

    def test_bash_scoped_commands(self):
        self.assertTrue(self.bash("python3 -m kb_distillery.search.query candidates tensor --scope scope-s"))
        self.assertTrue(self.bash("python3 -m kb_distillery.search.query candidates tensor --scope=scope-s --limit 5"))
        self.assertTrue(self.bash("python3 -m kb_distillery.search.query scope-status scope-s"))
        self.assertTrue(self.bash("python3 -m kb_distillery.search.explore_raw find tensor --scope scope-s"))
        self.assertTrue(self.bash("python3 -m kb_distillery.search.citations missing --scope scope-s"))
        self.assertTrue(self.bash("python3 -m kb_distillery.search.explore_raw read " + CLIP))
        self.assertTrue(self.bash("python3 -m kb_distillery.ingest resolve paper-a"))

    def test_bash_scoped_denials(self):
        self.assertFalse(self.bash("python3 -m kb_distillery.search.query candidates tensor"))
        self.assertFalse(self.bash("python3 -m kb_distillery.search.query candidates tensor --scope scope-other"))
        self.assertFalse(self.bash("python3 -m kb_distillery.search.query scope-status scope-other"))
        self.assertFalse(self.bash("python3 -m kb_distillery.search.query mocs"))
        self.assertFalse(self.bash("python3 -m kb_distillery.search.semfind theme theme-info-theory"))
        self.assertFalse(self.bash("python3 -m kb_distillery.search.explore_raw find tensor"))
        self.assertFalse(self.bash("python3 -m kb_distillery.search.explore_raw read raw/web-clips/other.md"))
        self.assertFalse(self.bash("python3 -m kb_distillery.search.citations missing"))
        self.assertFalse(self.bash("python3 -m kb_distillery.search.query candidates x --scope scope-s; ls"))

    def hook_decision(self, hook, tool, inp):
        out = asyncio.run(hook(dict(tool_name=tool, tool_input=inp), "1", None))
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_hook_uses_scope(self):
        hook = chat_agent.make_hook(scope=SCOPE)
        self.assertEqual(self.hook_decision(hook, "Read", fp(wiki("theme-info-theory"))), "deny")
        self.assertEqual(self.hook_decision(hook, "Read", fp(wiki("tensor-rank"))), "allow")
        self.assertEqual(self.hook_decision(chat_agent.make_hook(), "Read", fp(wiki("theme-info-theory"))), "allow")

    def test_custom_two_arg_policy_still_works_unscoped(self):
        hook = chat_agent.make_hook(policy=lambda name, inp: chat_agent.Decision(True))
        self.assertEqual(self.hook_decision(hook, "Read", dict()), "allow")


class ScopedPromptTests(unittest.TestCase):
    def test_agent_system_scoped(self):
        s = chat_agent.build_agent_system("Be brief.", scope=SCOPE)
        self.assertIn("Scope S (scope-s)", s)
        self.assertIn("[[tensor-rank]]", s)
        self.assertIn("[[paper-a]]", s)
        self.assertIn("cite only those pages", s)
        self.assertIn("End every answer with: Not yet digested in this scope:", s)
        self.assertIn(CLIP, s)
        self.assertIn("--scope scope-s", s)
        self.assertNotIn("## Scope", chat_agent.build_agent_system("Be brief."))

    def test_direct_system_scoped(self):
        s = chat_data.build_system("Be brief.", scope=SCOPE)
        self.assertIn("Not yet digested in this scope", s)
        self.assertIn(CLIP, s)
        self.assertNotIn("Tools: add", s)
        self.assertNotIn("## Scope", chat_data.build_system("Be brief."))

    def test_caps(self):
        big = dict(SCOPE, pages=set("p-" + str(i) for i in range(350)),
                   uncovered=[dict(path="raw/x/f" + str(i) + ".md", name="f", format="x") for i in range(130)])
        s = chat_data.scope_section(big, index=dict())
        self.assertEqual(s.count("\n- [[p-"), 300)
        self.assertIn("first 300 shown", s)
        self.assertIn("(130): ", s)
        self.assertIn("and 30 more", s)
        self.assertNotIn("f101.md", s)


class DirectRetrieveTests(VaultCase):
    def test_retrieve_filtered(self):
        everything = set(h["slug"] for h in chat_data.retrieve("tensor result", k=20))
        self.assertIn("paper-z", everything)
        ctx = sc.scope_context("scope-s", self.root)
        scoped = set(h["slug"] for h in chat_data.retrieve("tensor result", k=20, allowed=ctx["pages"]))
        self.assertTrue(scoped)
        self.assertTrue(scoped <= ctx["pages"])

    def test_plan_turn_scoped(self):
        ctx = sc.scope_context("scope-s", self.root)
        hits, new = chat_data.plan_turn([], "tensor result", scope=ctx)
        self.assertTrue(hits)
        self.assertTrue(set(new) <= ctx["pages"])
        self.assertNotIn("paper-z", new)
        hits, new = chat_data.plan_turn([], "tensor result")
        self.assertIn("paper-z", new)


if __name__ == "__main__":
    unittest.main()
