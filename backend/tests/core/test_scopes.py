#!/usr/bin/env python3
"""Scopes (schema 0.13): the pure projection, the lint checks, the 0007 migration, the dashboard
API (one kb(refine) step per write, in a temp git vault) and the public share profile."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kb.paths import vault_root
ROOT = vault_root()

from kb.core import coherence
from kb.lint import lint
from kb.core import scopes as sc

ENV = dict(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
A = "raw/printed-docs/2023-a.pdf"
B = "raw/printed-docs/2023-b.pdf"
C = "raw/printed-docs/2023-c.pdf"
D = "raw/printed-docs/2023-d.pdf"
IMG = "raw/images/2023-a-01.png"
ALL = sorted([A, B, C, D, IMG])


def page(typ, status, body="", **fm):
    from kb.core import schema
    typ = {"concept": "idea", "theme": "topic"}.get(typ, typ)
    lines = ["---", f"type: {typ}", f"layer: {schema.LAYER_OF[typ]}", f"status: {status}"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines + ["---", "", body]) + "\n"


def unit(slug, raw, links, digestion="full", status="digested"):
    body = f"# {slug}\n\nSee " + " ".join(f"[[{l}]]" for l in links)
    fm = dict(year=2023, area="[learning-theory]", raw=raw)
    fm["depth"] = digestion
    return page("paper", status, body, **fm)


def pages_of(texts):
    out = dict()
    for slug, text in texts.items():
        out[slug] = (f"wiki/{slug}.md", lint.parse_frontmatter(text), text)
    return out


TEXTS = dict()
TEXTS["paper-a"] = unit("paper-a", A, ["concept-x", "q-y"])
TEXTS["paper-b"] = unit("paper-b", B, ["concept-x"])
TEXTS["paper-c"] = unit("paper-c", C, ["concept-x"], digestion="listed", status="to-read")
TEXTS["concept-x"] = page("concept", "seed", "# concept-x\n")
TEXTS["q-y"] = page("question", "open", "# q-y\n")
TEXTS["theme-learning-theory"] = page("theme", "seed", "# T\n")
TEXTS["course-c"] = page("course", "growing", "# course\n")
TEXTS["nadav"] = page("person", "none", "# nadav\n")


def manifest():
    def row(path, disp, slug="", coll="", scopes=""):
        return dict(path=path, sha1="x", kind=path.split("/")[1], disposition=disp, slug=slug,
                    collection=coll, scopes=scopes)
    rows = [row(A, "source", "paper-a", "course-c,nadav", "scope-s"),
            row(B, "source", "paper-b", "course-c", "scope-s"),
            row(C, "queued", "", "course-c", "scope-s"),
            row(D, "skip", "", "", "scope-s"),
            row(IMG, "asset:" + A, "", "", "scope-s")]
    return dict((r["path"], r) for r in rows)


class PureTests(unittest.TestCase):
    def setUp(self):
        self.pages, self.m = pages_of(TEXTS), manifest()

    def test_rows(self):
        self.assertEqual(sc.rows_of("scope-s", self.m), ALL)
        self.assertEqual(sc.scopes_of_row(self.m[A]), ["scope-s"])
        self.assertEqual(sc.all_scopes(self.m), ["scope-s"])
        self.assertEqual(sc.all_scopes(dict()), [])

    def test_projection_hops_and_coverage(self):
        p = sc.projection(sc.rows_of("scope-s", self.m), self.pages, self.m)
        self.assertEqual(p["hop0"], ["paper-a", "paper-b", "paper-c"])
        self.assertEqual(p["hop1"], ["concept-x"])          # q-y is linked by one page only
        self.assertEqual(p["covered"], [A, B])
        self.assertEqual(p["uncovered"], [C])
        self.assertEqual(p["skipped"], [D])                 # the asset row is ignored outright
        self.assertAlmostEqual(p["coverage"], 2 / 3)
        self.assertEqual(p["hubs"], ["course-c"])
        self.assertEqual(p["themes"], ["theme-learning-theory"])
        self.assertIsNone(sc.projection([D], self.pages, self.m)["coverage"])

    def test_resolve_each_node_kind(self):
        def r(*ids):
            return sc.resolve(list(ids), self.pages, self.m)
        self.assertEqual(r("course-c"), [A, B, C])
        self.assertEqual(r("nadav"), [A])
        self.assertEqual(r("theme-learning-theory"), [A, B, C])
        self.assertEqual(r("concept-x"), [A, B, C])
        self.assertEqual(r("q-y"), [A])
        self.assertEqual(r("paper-b"), [B])
        self.assertEqual(r("raw:" + D), [D])
        self.assertEqual(r("raw:" + IMG), [])               # companions ride with their parent
        self.assertEqual(r("raw:raw/inbox/x.pdf", "nope"), [])
        self.assertEqual(r("paper-a", "paper-a", "raw:" + A), [A])

    def test_render_and_replace_are_idempotent(self):
        p = sc.projection(sc.rows_of("scope-s", self.m), self.pages, self.m)
        out = sc.render_members("scope-s", p, self.pages)
        self.assertIn("**Coverage:** 2/3 files digested (67%) · 1 undigested", out)
        for h in ("### Covered", "### Uncovered", "### Context"):
            self.assertIn(h, out)
        self.assertEqual(out, sc.render_members("scope-s", p, self.pages))
        tpl = ("---\ntype: scope\n---\n\n# S\n\n## Why\n\nBecause [[q-y]].\n\n## Members\n\nold\n\n"
               "## Notes\n\nkeep me\n")
        once = sc.replace_members(tpl, out)
        self.assertEqual(once, sc.replace_members(once, out))
        self.assertIn("Because [[q-y]].", once)
        self.assertIn("## Notes\n\nkeep me\n", once)
        self.assertNotIn("old", once)
        tail = "# S\n\n## Why\n\nw\n\n## Members\n\nold\n"
        t1 = sc.replace_members(tail, out)
        self.assertEqual(t1, sc.replace_members(t1, out))
        self.assertIn("## Members", sc.replace_members("# S\n", out))

    def test_write_scope_rows_adds_and_removes(self):
        m = manifest()
        added, removed = sc.write_scope_rows(m, "scope-t", [A, B])
        self.assertEqual(added, [A, B])
        self.assertEqual(sc.scopes_of_row(m[A]), ["scope-s", "scope-t"])
        added, removed = sc.write_scope_rows(m, "scope-t", [B])
        self.assertEqual(removed, [A])
        self.assertEqual(sc.scopes_of_row(m[A]), ["scope-s"])
        self.assertEqual(sc.delete_scope(m, "scope-s"), ALL)
        self.assertEqual(sc.all_scopes(m), ["scope-t"])

    def test_why_helpers(self):
        t = "# S\n\n## Why\n\n<!-- hint -->\n\n## Members\n"
        self.assertEqual(sc.why_text(t), "")
        t2 = sc.set_why(t, "Real [[theme-learning-theory]] reason.")
        self.assertEqual(sc.why_links(t2), ["theme-learning-theory"])
        self.assertIn("## Members", t2)


def paper_page(slug, raw):
    body = "# " + slug + "\n\nOne line.\n\n## Problem\nx\n"
    fm = dict(year=2023, area="[learning-theory]", raw=raw)
    fm["depth"] = "full"
    return page("paper", "digested", body, **fm)


SCOPE_PAGE = ("---\ntype: scope\nlayer: collection\nstatus: active\nrelated: []\naliases: []\n---\n\n# S\n\n## Why\n\n"
              "Because [[q-y]] matters.\n\n## Members\n\n<!-- generated: scopes -->\n")


class LintVaultTests(unittest.TestCase):
    """A tiny temp vault through the real collect_snapshot (same seams as test_lint_ci)."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-scopes-")
        for d in ("wiki", "meta", "raw/printed-docs"):
            os.makedirs(os.path.join(self.root, d))
        self.addCleanup(shutil.rmtree, self.root, True)
        for p in (A, B, C):
            with open(os.path.join(self.root, p), "wb") as f:
                f.write(b"%PDF-1.4\n" + p.encode() * 200)
        self.put("wiki/paper-a.md", paper_page("paper-a", A))
        self.put("wiki/paper-b.md", paper_page("paper-b", B))
        self.put("wiki/q-y.md", page("question", "open", "# Y\n\nWhat?\n"))
        self.put("wiki/scope-s.md", SCOPE_PAGE)
        self.cells = dict()
        self.cells[A] = "scope-s"
        self.cells[C] = "scope-s"
        self.write_corpus()
        self.patches = [mock.patch.object(lint, "ROOT", self.root),
                        mock.patch.object(coherence, "ROOT", self.root),
                        mock.patch.object(coherence, "WARNINGS_PATH",
                                          os.path.join(self.root, "meta", "coherence-warnings.tsv"))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lint.CI_RAW.clear)

    def put(self, rel, text):
        Path(self.root, rel).write_text(text, encoding="utf-8")

    def write_corpus(self):
        lines = ["path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes"]
        for p in (A, B, C):
            lines.append("\t".join([p, "", "printed-docs", "queued", "", "", self.cells.get(p, "")]))
        self.put("meta/corpus.tsv", "\n".join(lines) + "\n")

    def run_lint(self, **env):
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
            return lint.collect_snapshot()

    def text(self, rel="wiki/scope-s.md"):
        return Path(self.root, rel).read_text(encoding="utf-8")

    def test_valid_scope_regenerates_members_idempotently(self):
        snap = self.run_lint()
        self.assertEqual(snap["values"]["errors"], 0, lint.errors)
        self.assertEqual(snap["values"]["scopes"], 1)
        self.assertEqual(snap["values"]["scope_uncovered"], 1)
        first = self.text()
        self.assertIn("**Coverage:** 1/2 files digested (50%) · 1 undigested", first)
        self.assertIn("[[paper-a]]", first)
        self.assertIn("Because [[q-y]] matters.", first)
        self.run_lint()
        self.assertEqual(self.text(), first)
        with open(os.path.join(self.root, "meta", "corpus.tsv"), encoding="utf-8") as f:
            self.assertTrue(any(l.endswith("\tscope-s") for l in f.read().splitlines()))

    def test_cell_without_a_scope_page_is_an_error(self):
        self.cells[B] = "scope-ghost"
        self.write_corpus()
        self.run_lint()
        self.assertTrue(any("scope-ghost" in e and "not a scope page" in e for e in lint.errors), lint.errors)

    def test_empty_why_is_an_error_and_no_rows_a_warning(self):
        self.put("wiki/scope-s.md", SCOPE_PAGE.replace("Because [[q-y]] matters.", "<!-- todo -->"))
        self.cells.clear()
        self.write_corpus()
        self.run_lint()
        self.assertTrue(any("non-empty ## Why" in e for e in lint.errors), lint.errors)
        self.assertTrue(any("scope has no files" in w for w in lint.warnings), lint.warnings)

    def test_deleted_file_is_reported_as_lost(self):
        os.remove(os.path.join(self.root, C))
        self.run_lint()
        self.assertTrue(any("scope-s lost " + C in w for w in lint.warnings), lint.warnings)

    def test_ci_mode_leaves_the_page_alone(self):
        before = self.text()
        self.run_lint(KB_CI="1")
        self.assertEqual(self.text(), before)


class MigrationTests(unittest.TestCase):
    def load(self):
        path = os.path.join(ROOT, "backend", "src", "kb", "migrations", "0007_scopes_column.py")
        spec = importlib.util.spec_from_file_location("m0007", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_adds_an_empty_column_once(self):
        mod = self.load()
        self.assertEqual(mod.PRODUCES, (0, 13))
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "meta"))
            path = os.path.join(root, "meta", "corpus.tsv")
            old = ("# Generated\n# note\npath\tsha1\tkind\tdisposition\tslug\tcollection\n"
                   "raw/a.pdf\tabc\tprinted-docs\tqueued\t\t\nraw/b.pdf\tdef\tprinted-docs\tdigested\tp\tc1,c2\n")
            Path(path).write_text(old)
            mod.apply(root)
            once = Path(path).read_text()
            lines = once.split("\n")
            self.assertEqual(lines[2], "path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes")
            self.assertEqual([len(l.split("\t")) for l in lines[3:5]], [7, 7])
            self.assertTrue(lines[0].startswith("#"))
            mod.apply(root)
            self.assertEqual(Path(path).read_text(), once)
            mod.apply(os.path.join(root, "missing"))          # no corpus: a no-op


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout.strip()


class ApiTests(unittest.TestCase):
    """scopes_data against a temp git vault: every write is exactly one kb(refine) step."""

    def setUp(self):
        from kb.services import scopes as scopes_data
        from kb.ops import core
        self.sd, self.core = scopes_data, core
        env = mock.patch.dict(os.environ, dict(ENV, KB_NO_PUSH="1"))
        env.start()
        self.addCleanup(env.stop)
        trig = mock.patch("kb.share.autodeploy.trigger", return_value="skipped")
        trig.start()
        self.addCleanup(trig.stop)
        self.root = tempfile.mkdtemp(prefix="kb-scopes-api-")
        self.addCleanup(shutil.rmtree, self.root, True)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "t")
        git(self.root, "config", "user.email", "t@t")
        _lint = mock.patch("kb.ops.core.run_lint", return_value=None)  # lint of a bare temp repo is not under test
        _lint.start()
        self.addCleanup(_lint.stop)
        files = dict()
        files["meta/stub.py"] = "x = 1\n"
        files["meta/log.md"] = "# log\n"
        files[".gitignore"] = "meta/.ops/\n"
        files["index.md"] = "v1\n"
        files["meta/templates/scope.md"] = Path(ROOT, "meta", "templates", "scope.md").read_text()
        for slug, text in TEXTS.items():
            files[f"wiki/{slug}.md"] = text
        m = manifest()
        for r in m.values():
            r["scopes"] = ""
        lines = ["path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes"]
        for p in sorted(m):
            r = m[p]
            lines.append("\t".join([p, r["sha1"], r["kind"], r["disposition"], r["slug"], r["collection"], ""]))
        files["meta/corpus.tsv"] = "\n".join(lines) + "\n"
        for rel, text in files.items():
            Path(self.root, rel).parent.mkdir(parents=True, exist_ok=True)
            Path(self.root, rel).write_text(text)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "chore: init (retro)")

    def commits(self):
        return int(git(self.root, "rev-list", "--count", "HEAD"))

    def files_of_head(self):
        return sorted(git(self.root, "show", "--name-only", "--format=", "HEAD").splitlines())

    def save(self, **kw):
        payload = dict(slug="alpha", title="Alpha set", why="Because [[q-y]] needs it.", paths=[A, C], create=True)
        payload.update(kw)
        return self.sd.save_scope(payload, root=self.root, lint=False, push=False)

    def test_create_update_duplicate_delete_are_one_step_each(self):
        n = self.commits()
        res = self.save()
        self.assertTrue(res["ok"] and res["sha"])
        self.assertEqual(res["slug"], "scope-alpha")
        from kb.core import schema
        self.assertRegex(res["version"], rf"^kb-{schema.SCHEMA_VERSION[0]}\.{schema.SCHEMA_VERSION[1]}\.\d+$")
        self.assertEqual(self.commits(), n + 1)
        self.assertTrue(git(self.root, "log", "-1", "--format=%s").startswith("kb(refine): "))
        self.assertEqual(self.files_of_head(), ["meta/corpus.tsv", "wiki/scope-alpha.md"])
        text = Path(self.root, "wiki", "scope-alpha.md").read_text()
        self.assertIn("# Alpha set", text)
        self.assertIn("Because [[q-y]] needs it.", text)
        self.assertIn("**Coverage:** 1/2 files digested (50%) · 1 undigested", text)
        got = self.sd.get_scope("scope-alpha", root=self.root)
        self.assertEqual([r["path"] for r in got["rows"]], [A, C])
        self.assertEqual(got["projection"]["uncovered"], [C])
        listing = self.sd.list_scopes(root=self.root)["scopes"]
        self.assertEqual([(s["slug"], s["files"], s["digested"], s["uncovered"]) for s in listing],
                         [("scope-alpha", 2, 1, 1)])

        self.save(paths=[B], create=False, why="Now about [[theme-learning-theory]].", title="")
        self.assertEqual(self.commits(), n + 2)
        self.assertEqual(self.files_of_head(), ["meta/corpus.tsv", "wiki/scope-alpha.md"])
        self.assertEqual(sc.rows_of("scope-alpha", lint.read_manifest(self.root)), [B])
        self.assertIn("# Alpha set", Path(self.root, "wiki", "scope-alpha.md").read_text())

        self.sd.duplicate_scope(dict(slug="scope-alpha", new_slug="beta"), root=self.root, lint=False, push=False)
        self.assertEqual(self.commits(), n + 3)
        self.assertEqual(self.files_of_head(), ["meta/corpus.tsv", "wiki/scope-beta.md"])
        self.assertEqual(sc.rows_of("scope-beta", lint.read_manifest(self.root)), [B])

        self.sd.delete_scope(dict(slug="scope-alpha"), root=self.root, lint=False, push=False)
        self.assertEqual(self.commits(), n + 4)
        self.assertEqual(self.files_of_head(), ["meta/corpus.tsv", "wiki/scope-alpha.md"])
        self.assertFalse(Path(self.root, "wiki", "scope-alpha.md").exists())
        self.assertEqual(sc.all_scopes(lint.read_manifest(self.root)), ["scope-beta"])
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def test_refusals(self):
        def code(**kw):
            with self.assertRaises(self.sd.ScopeError) as cm:
                self.save(**kw)
            return cm.exception.status
        n = self.commits()
        self.assertEqual(code(why="  "), 400)
        self.assertEqual(code(slug="Bad Slug!"), 400)
        self.assertEqual(code(paths=["raw/inbox/x.pdf"]), 400)
        self.assertEqual(code(paths=["raw/printed-docs/nope.pdf"]), 400)
        self.assertEqual(code(paths=[IMG]), 400)                       # an asset row
        self.assertEqual(code(create=False), 404)
        self.save()
        self.assertEqual(code(), 409)                                  # already exists
        self.core.begin("refine", "something", root=self.root)
        self.assertEqual(code(slug="gamma"), 409)                      # another ops session is open
        self.assertEqual(self.commits(), n + 1)

    def test_resolve_nodes(self):
        res = self.sd.resolve_nodes(["course-c", "raw:" + D], root=self.root)
        self.assertEqual(res["paths"], [A, B, C, D])
        self.assertEqual([r["disposition"] for r in res["rows"]], ["source", "source", "queued", "skip"])
        self.assertEqual(res["rows"][0]["page_type"], "paper")
        with self.assertRaises(self.sd.ScopeError):
            self.sd.resolve_nodes("course-c", root=self.root)


class ShareProfileTests(unittest.TestCase):
    def test_public_profile_drops_scope_pages_and_the_scopes_key(self):
        from kb.share import build as sb
        self.assertIn("scope", sb.PUBLIC_EXCLUDE_TYPES)
        self.assertTrue(sb.PUBLIC_EXCLUDE_TYPES.isdisjoint({"conversation", "ai-chat", "person"}))   # chats and profiles are public (only email-derived pages go)
        self.assertIn("scopes", sb.PUBLIC_DROP_KEYS)
        self.assertIn("/api/scopes", sb.SHIMMED_API)
        self.assertIn("/api/scope", sb.SHIMMED_API)
        nodes = [dict(id="paper-a", type="paper", properties=dict(scopes="scope-s", raw=A)),
                 dict(id="scope-s", type="scope", properties=dict())]
        links = [dict(source="scope-s", target="paper-a")]
        data = dict(graph=dict(nodes=nodes, links=links, facets=dict()),
                    index=dict(pages=[dict(id="paper-a", type="paper"), dict(id="scope-s", type="scope")],
                               links=[["scope-s", "paper-a"]], wanted=[]),
                    pages=dict())
        data["pages"]["paper-a"] = dict(card=dict(type="paper"), frontmatter=dict(scopes="scope-s"),
                                        backlinks=[dict(id="scope-s")], outbound=[], suggested=[])
        data["pages"]["scope-s"] = dict(card=dict(type="scope"), frontmatter=dict(), backlinks=[],
                                        outbound=["paper-a"], suggested=[])
        out = sb.apply_profile(data, "public")
        self.assertEqual([n["id"] for n in out["graph"]["nodes"]], ["paper-a"])
        self.assertEqual(out["graph"]["links"], [])
        self.assertEqual(list(out["pages"]), ["paper-a"])
        self.assertEqual(out["pages"]["paper-a"]["backlinks"], [])
        self.assertNotIn("scopes", out["pages"]["paper-a"]["frontmatter"])
        self.assertNotIn("scopes", out["graph"]["nodes"][0]["properties"])
        self.assertNotIn("scope-s", json.dumps(out))

    def test_scoped_public_build_keeps_only_the_scope_set_and_names_nothing_else(self):
        from kb.share import build as sb
        nodes = [dict(id="paper-a", type="paper", title="A", preview="see [[paper-b]]",
                      properties=dict(related="paper-b, idea-x")),
                 dict(id="paper-b", type="paper", title="Bee paper", properties=dict()),
                 dict(id="idea-x", type="idea", title="X", properties=dict())]
        links = [dict(source="paper-a", target="paper-b"), dict(source="paper-a", target="idea-x")]
        data = dict(graph=dict(nodes=nodes, links=links, facets=dict()),
                    index=dict(pages=[dict(id=n["id"], type=n["type"]) for n in nodes],
                               links=[["paper-a", "paper-b"], ["paper-a", "idea-x"]], wanted=[]),
                    pages={n["id"]: dict(card=dict(type=n["type"], title=n["title"]), frontmatter=dict(),
                                         markdown="", backlinks=[], outbound=[], suggested=[]) for n in nodes})
        data["pages"]["paper-a"].update(markdown="cites [[paper-b|B]] and [[paper-b]], uses [[idea-x]]",
                                        frontmatter=dict(related=["paper-b", "idea-x"]), outbound=["paper-b", "idea-x"])
        data["pages"]["paper-b"]["backlinks"] = [dict(id="paper-a")]
        out = sb.apply_profile(data, "public", {"paper-a", "idea-x"})
        self.assertEqual(sorted(out["pages"]), ["idea-x", "paper-a"])
        self.assertEqual([l["target"] for l in out["graph"]["links"]], ["idea-x"])
        self.assertEqual(out["pages"]["paper-a"]["markdown"], "cites B and Bee paper, uses [[idea-x]]")
        self.assertEqual(out["pages"]["paper-a"]["frontmatter"]["related"], ["idea-x"])
        self.assertNotIn("paper-b", json.dumps(out))


if __name__ == "__main__":
    unittest.main()
