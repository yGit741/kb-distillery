#!/usr/bin/env python3
"""Tests for src/kb_distillery/publish/site/build.py — the builder of the shared site (the React app + the wiki data of a ref).

Synthetic cases use a temp git repo with a tiny vault and a stub frontend dist (`vite build` is not run here, see
test_share_app.RealFrontendTests); the real repo is used read-only for the tag builds (skipped when git or the kb-* tags
are unavailable). The viewer is always this worktree's code (`viewer_worktree=True`), so the uncommitted builder is what
gets exercised.
"""
import atexit
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.publish.site import build as sb

REAL_TAGS = ("kb-0.8.0", "kb-0.8.6", "kb-0.9.6")
THINK_SECRET = "THINK-SECRET-TOKEN-7f3a9c"
SECRET_RAW = "raw/papers/secret-paper.pdf"
SECRET_EMAIL = "someone@example.com"
KB_DATA_RE = re.compile(r'<script type="application/json" id="kb-data">(.*?)</script>', re.S)

PAGES = {
    "alpha.md": f"""---
type: concept
maturity: seed
raw: {SECRET_RAW}
email: {SECRET_EMAIL}
original_name: Old Name.md
related: [beta]
---

# Ünïcode ∂ title — with spaces

A concept linking [[beta]] and a [[missing-page]] that does not exist.

![[x.png]]

$$
\\int_0^1 x\\,dx = \\tfrac12
$$

Inline $e^{{i\\pi}}$ too. Mentions `raw/notes/scratch.md` in prose.
""",
    "beta.md": """---
type: moc
maturity: growing
---

# Beta theme

Old-schema MOC. Links [[alpha]], [[gamma]] and [[delta]].
""",
    "gamma.md": """---
type: distilled-think
maturity: review
---

# Gamma review

Transient page linking [[alpha]]. GAMMA-ONLY-TOKEN.
""",
    "delta.md": """---
type: paper
maturity: digested
year: 2021
area: [learning-theory]
---

# Delta paper

Cites [[alpha]] and [[beta]].
""",
    "nofm.md": "# No frontmatter here\n\nJust text linking [[alpha]].\n",
}


def _git(root, *args, check=True):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=check)


def _have_git():
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


def _have_tags():
    return _have_git() and all(
        subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{t}"], cwd=ROOT,
                       capture_output=True).returncode == 0 for t in REAL_TAGS)


def make_repo(base, pages=PAGES, with_think=True, with_raw=True):
    """A git repo with one kb commit holding `pages` under wiki/, a think/ file and a gitignored png."""
    root = os.path.join(base, "repo")
    os.makedirs(root)
    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    with open(os.path.join(root, ".gitignore"), "w") as f:
        f.write("raw/**/*.png\n")
    if pages:
        os.makedirs(os.path.join(root, "wiki"))
        for name, text in pages.items():
            with open(os.path.join(root, "wiki", name), "w", encoding="utf-8") as f:
                f.write(text)
    if with_think:
        os.makedirs(os.path.join(root, "think"))
        with open(os.path.join(root, "think", "secret.md"), "w") as f:
            f.write(f"# private\n\n{THINK_SECRET}\n")
    if with_raw:
        os.makedirs(os.path.join(root, "raw", "images"))
        with open(os.path.join(root, "raw", "images", "x.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    _git(root, "add", "-A")
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-01-02T03:04:05+00:00",
               GIT_COMMITTER_DATE="2026-01-02T03:04:05+00:00")
    subprocess.run(["git", "commit", "-q", "-m", "kb(import): fixture (kb-0.1.1)\n\nKB-Version: 0.1.1\nKB-Op: import"],
                   cwd=root, env=env, check=True, capture_output=True)
    return root


STUB_INDEX = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Thesis KB</title>
    <script type="module" crossorigin src="/assets/index-abc123.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index-abc123.css">
  </head>
  <body><div id="root"></div></body>
</html>
"""


def make_stub_dist(base, name="dist"):
    """A built-app lookalike (a template index.html + assets/) so nothing here needs node."""
    dist = Path(base) / name
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(STUB_INDEX, encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log('app');\n", encoding="utf-8")
    (dist / "assets" / "index-abc123.css").write_text("body{margin:0}\n", encoding="utf-8")
    (dist / ".src-hash").write_text("x\n", encoding="utf-8")        # a stamp must never ship
    return dist


_STUB = []


def default_dist():
    if not _STUB:
        tmp = tempfile.mkdtemp(prefix="share-stub-dist-")
        atexit.register(shutil.rmtree, tmp, True)
        _STUB.append(make_stub_dist(tmp))
    return _STUB[0]


def build_from(repo, out, profile="private", ref="main", **kw):
    """The worktree's builder on `repo`; `frontend_dist` defaults to a stub (pass None to run the real vite build)."""
    kw.setdefault("frontend_dist", default_dist())
    return sb.build(ref, profile=profile, root=repo, viewer_root=ROOT, viewer_worktree=True,
                    out_root=out, **kw)


def read_html(result):
    return (result.dir / "index.html").read_text(encoding="utf-8")


def kb_data(html):
    return json.loads(KB_DATA_RE.search(html).group(1))


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _have_git():
            raise unittest.SkipTest("git not available")
        cls.tmp = tempfile.mkdtemp(prefix="share-test-")
        cls.repo = make_repo(cls.tmp)
        cls.out = os.path.join(cls.tmp, "out")
        cls.private = build_from(cls.repo, cls.out, "private", label="private")
        cls.public = build_from(cls.repo, cls.out, "public", label="public")
        cls.html = read_html(cls.private)
        cls.data = kb_data(cls.html)
        cls.pub_html = read_html(cls.public)
        cls.pub_data = kb_data(cls.pub_html)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class FixtureBuildTests(_Fixture):
    def test_manifest_and_output(self):
        m = self.private.manifest
        self.assertEqual(m.kb_version, "0.1.1")
        self.assertEqual(m.profile, "private")
        self.assertEqual(m.built_at, "2026-01-02T03:04:05Z")
        self.assertEqual(m.content_sha, _git(self.repo, "rev-parse", "main").stdout.strip())
        self.assertEqual(m.layout, "app")
        self.assertEqual(m.sha256, sb.tree_digest(self.private.dir))
        on_disk = sb.Manifest.from_json((self.private.dir / "manifest.json").read_text())
        self.assertEqual(on_disk, m)
        meta = self.data["meta"]               # what the app's footer line shows
        self.assertEqual((meta["kb_version"], meta["content_sha"], meta["viewer_sha"], meta["profile"], meta["built_at"]),
                         ("0.1.1", m.content_sha, m.viewer_sha, "private", m.built_at))

    def test_data_shape(self):
        nodes = {n["id"] for n in self.data["graph"]["nodes"]}
        self.assertEqual(nodes, {"alpha", "beta", "gamma", "delta"})  # nofm.md has no frontmatter
        self.assertEqual(set(self.data["pages"]), nodes)
        self.assertEqual({c["id"] for c in self.data["index"]["pages"]}, nodes)
        self.assertEqual(self.data["graph"]["generated_at"], "2026-01-02T03:04:05Z")
        self.assertIn("moc", self.data["graph"]["facets"]["types"])
        alpha = self.data["pages"]["alpha"]
        self.assertEqual(alpha["card"]["title"], "Ünïcode ∂ title — with spaces")
        self.assertIn("Ünïcode ∂ title — with spaces", self.html)  # ensure_ascii=False
        self.assertIn("missing-page", alpha["broken"])  # dangling wikilink: rendered as wanted, no crash
        self.assertIn("$$\n\\int_0^1", alpha["markdown"])
        self.assertEqual(alpha["card"]["mtime"], 1767323045)  # commit date, not file mtime

    def test_isolation_think_and_raw(self):
        self.assertNotIn(THINK_SECRET, self.html)
        self.assertNotIn(THINK_SECRET, self.pub_html)
        self.assertNotIn("data:image", self.html)
        self.assertIn("![[x.png]]", self.data["pages"]["alpha"]["markdown"])

    def test_private_keeps_fields(self):
        node = next(n for n in self.data["graph"]["nodes"] if n["id"] == "alpha")
        self.assertEqual(node["path"], "wiki/alpha.md")
        self.assertEqual(node["properties"]["raw"], SECRET_RAW)
        fm = self.data["pages"]["alpha"]["frontmatter"]
        self.assertEqual(fm["email"], SECRET_EMAIL)
        self.assertEqual(fm["original_name"], "Old Name.md")
        self.assertIn("gamma", self.data["pages"])

    def test_public_drops_fields_and_distilled_think(self):
        html, data = self.pub_html, self.pub_data
        self.assertNotIn(SECRET_RAW, html)
        self.assertNotIn(SECRET_EMAIL, html)
        self.assertNotIn("original_name", html)
        self.assertNotIn("Old Name.md", html)
        self.assertNotIn("GAMMA-ONLY-TOKEN", html)
        self.assertNotIn("distilled-think", json.dumps(data))
        for data_ in (data, self.data):                # the raw data layer is never exported
            for key in ("raw_nodes", "raw_links", "piles", "pile_links"):
                self.assertNotIn(key, data_["graph"])
        for n in data["graph"]["nodes"]:
            self.assertNotIn("path", n)
            for k in sb.PUBLIC_DROP_KEYS:
                self.assertNotIn(k, n["properties"])
        for p in data["pages"].values():
            self.assertNotIn("path", p)
            for k in sb.PUBLIC_DROP_KEYS:
                self.assertNotIn(k, p["frontmatter"])
            self.assertNotIn("gamma", p["outbound"])
            self.assertNotIn("gamma", [b["id"] for b in p["backlinks"]])
        ids = {n["id"] for n in data["graph"]["nodes"]}
        self.assertEqual(ids, {"alpha", "beta", "delta"})
        self.assertEqual(data["graph"]["node_count"], 3)
        self.assertEqual(data["graph"]["link_count"], len(data["graph"]["links"]))
        for l in data["graph"]["links"]:
            self.assertNotIn("gamma", (l["source"], l["target"]))
        for l in data["index"]["links"]:
            self.assertNotIn("gamma", l)
        self.assertIn("raw/notes/scratch.md", html)  # prose is not scrubbed; that is audit's job (W2b)

    def test_the_page_is_a_static_app_not_a_shell(self):
        for html in (self.html, self.pub_html):
            self.assertNotIn("127.0.0.1", html)
            self.assertNotIn("localhost", html)
            self.assertNotIn("<iframe", html)
            self.assertNotIn("srcdoc", html)
            self.assertNotIn("/admin/", html)
            self.assertEqual(html.count('id="kb-data"'), 1)
            self.assertIn('<script type="module" crossorigin src="/assets/index-abc123.js"></script>', html)

    def test_reproducible_dirty_tree_and_clone(self):
        again = build_from(self.repo, self.out, "private", label="again")
        self.assertEqual(again.manifest.sha256, self.private.manifest.sha256)
        self.assertEqual(sha256(again.dir / "index.html"), sha256(self.private.dir / "index.html"))
        # dirty working tree + untracked page: no effect
        with open(os.path.join(self.repo, "wiki", "alpha.md"), "a") as f:
            f.write("\nDIRTY-EDIT-TOKEN\n")
        with open(os.path.join(self.repo, "wiki", "junk.md"), "w") as f:
            f.write("---\ntype: concept\n---\n\n# Junk\n\nJUNK-TOKEN\n")
        try:
            dirty = build_from(self.repo, self.out, "private", label="dirty")
        finally:
            _git(self.repo, "checkout", "--", "wiki/alpha.md")
            os.remove(os.path.join(self.repo, "wiki", "junk.md"))
        self.assertEqual(dirty.manifest.sha256, self.private.manifest.sha256)
        self.assertNotIn("JUNK-TOKEN", read_html(dirty))
        # second clone: identical bytes
        clone = os.path.join(self.tmp, "clone")
        _git(self.tmp, "clone", "-q", self.repo, clone)
        cloned = build_from(clone, self.out, "private", label="clone")
        self.assertEqual(cloned.manifest.sha256, self.private.manifest.sha256)
        self.assertEqual(cloned.manifest.content_sha, self.private.manifest.content_sha)

    def test_versions(self):
        rows = sb.versions(self.repo)
        self.assertEqual([r["version"] for r in rows], ["0.1.1"])
        self.assertEqual(rows[0]["sha"], self.private.manifest.content_sha)
        self.assertEqual(sb.versions(self.repo, rev=self.private.manifest.content_sha), rows)

    def test_reproducible_after_new_tag(self):
        _git(self.repo, "tag", "kb-0.1.1-later")
        try:
            again = build_from(self.repo, self.out, "private", label="tagged")
        finally:
            _git(self.repo, "tag", "-d", "kb-0.1.1-later")
        self.assertEqual(again.manifest.sha256, self.private.manifest.sha256)

    def test_unknown_ref_and_profile(self):
        with self.assertRaises(sb.BuildError) as cm:
            build_from(self.repo, self.out, ref="no-such-ref")
        self.assertIn("unknown ref 'no-such-ref'", str(cm.exception))
        with self.assertRaises(sb.BuildError):
            build_from(self.repo, self.out, ref="9.9.9")
        with self.assertRaises(sb.BuildError):
            build_from(self.repo, self.out, profile="secret")

    def test_bare_version_resolves_via_trailer(self):
        self.assertEqual(sb.resolve_ref(self.repo, "0.1.1"), self.private.manifest.content_sha)
        self.assertEqual(sb.resolve_ref(self.repo, "kb-0.1.1"), self.private.manifest.content_sha)

    def test_viewer_without_share_module_is_clear_error(self):
        # the fixture repo has no share builder at all → a clear error, no traceback
        with self.assertRaises(sb.BuildError) as cm:
            sb.build("main", root=self.repo, viewer_root=self.repo, out_root=self.out, label="noviewer",
                     frontend_dist=default_dist())
        self.assertIn("no app-layout share builder", str(cm.exception))
        self.assertNotIn("Traceback", str(cm.exception))

    def test_cli(self):
        from kb_distillery.publish.cloudflare import __main__ as share_main
        with contextlib.redirect_stdout(io.StringIO()) as so:
            self.assertEqual(share_main.main(["versions", "--root", self.repo]), 0)
        self.assertIn("kb-0.1.1", so.getvalue())
        with contextlib.redirect_stderr(io.StringIO()) as se:
            rc = share_main.main(["build", "no-such-ref", "--root", self.repo])
        self.assertEqual(rc, 1)  # a BuildError is one line on stderr, not a traceback
        self.assertIn("unknown ref", se.getvalue())


class EmptyWikiTests(unittest.TestCase):
    def setUp(self):
        if not _have_git():
            self.skipTest("git not available")
        self.tmp = tempfile.mkdtemp(prefix="share-empty-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_wiki_builds_an_empty_blob(self):
        repo = make_repo(self.tmp, pages={}, with_raw=False)
        res = build_from(repo, os.path.join(self.tmp, "out"))
        data = kb_data(read_html(res))
        self.assertEqual(data["graph"]["nodes"], [])
        self.assertEqual(data["pages"], {})


class EmbedJsonTests(unittest.TestCase):
    def test_embed_json_escapes_script_terminators(self):
        s = sb.embed_json({"x": "</script><!--"})
        self.assertNotIn("</", s)
        self.assertNotIn("<!--", s)
        self.assertEqual(json.loads(s), {"x": "</script><!--"})


class SizeVerdictTests(unittest.TestCase):
    """The deployable size is the builder's knowledge, not a number a test guessed (10 MB was
    one; the vault outgrew it with the Kalai blog and every PR gate went red)."""

    def test_fine_below_warning(self):
        self.assertIsNone(sb.size_verdict(sb.WARN_HTML_BYTES))

    def test_warns_near_the_limit(self):
        self.assertIn("Cloudflare", sb.size_verdict(sb.WARN_HTML_BYTES + 1))

    def test_refuses_above_the_limit(self):
        with self.assertRaises(sb.BuildError):
            sb.size_verdict(sb.MAX_HTML_BYTES + 1)


class RealRepoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _have_tags():
            raise unittest.SkipTest("real kb-* tags not available")
        cls.tmp = tempfile.mkdtemp(prefix="share-real-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _counts(self, sha):
        """node/link counts straight from graph_data on an archive of `sha` (independent process)."""
        content = os.path.join(self.tmp, "content-" + sha[:7])
        sb.archive(ROOT, sha, content)
        code = ("import json,sys; from kb_distillery.graph import snapshot as graph_data; "
                "s = graph_data.build_graph_snapshot(); print(json.dumps([s['node_count'], s['link_count']]))")
        env = dict(os.environ, KB_ROOT=content, PYTHONHASHSEED="0")
        p = subprocess.run([sys.executable, "-c", code, os.path.join(ROOT, "meta")],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_tags_and_main(self):
        for ref in REAL_TAGS + ("main",):
            with self.subTest(ref=ref):
                res = sb.build(ref, root=ROOT, viewer_root=ROOT, viewer_worktree=True, out_root=self.tmp,
                               frontend_dist=default_dist())
                html = read_html(res)
                self.assertLessEqual(len(html.encode("utf-8")), sb.MAX_HTML_BYTES)
                data = kb_data(html)
                ids = {n["id"] for n in data["graph"]["nodes"]}
                self.assertTrue(ids)
                self.assertEqual(ids, set(data["pages"]))
                self.assertEqual(ids, {c["id"] for c in data["index"]["pages"]})
                self.assertEqual([data["graph"]["node_count"], data["graph"]["link_count"]],
                                 self._counts(res.manifest.content_sha))
                self.assertNotIn("127.0.0.1", html)
                if ref != "main":
                    self.assertEqual(res.manifest.kb_version, ref[3:])

    def test_tag_resolves_to_tag_commit(self):
        sha = _git(ROOT, "rev-parse", "kb-0.9.6^{commit}").stdout.strip()
        self.assertEqual(sb.resolve_ref(ROOT, "kb-0.9.6"), sha)
        self.assertEqual(sb.resolve_ref(ROOT, "0.9.6"), sha)
        res = sb.build("kb-0.9.6", root=ROOT, viewer_root=ROOT, viewer_worktree=True, out_root=self.tmp,
                       label="tag-check", frontend_dist=default_dist())
        self.assertEqual(res.manifest.content_sha, sha)
        self.assertEqual(res.manifest.built_at, _git(ROOT, "show", "-s", "--format=%cI", sha).stdout.strip())

    def test_old_viewer_without_share_module(self):
        with self.assertRaises(sb.BuildError) as cm:
            sb.build("main", viewer_ref="kb-0.8.0", root=ROOT, out_root=self.tmp, label="old-viewer",
                     frontend_dist=default_dist())
        msg = str(cm.exception)
        self.assertIn("no app-layout share builder", msg)
        self.assertNotIn("Traceback", msg)


if __name__ == "__main__":
    unittest.main()


MAIL_PAGES = {
    "hub.md": "---\ntype: concept\nmaturity: seed\n---\n\n# Hub\n\nSee [[mail-thread]], [[mail-list]], [[llm-chat]] and [[jane]].\n",
    "mail-thread.md": "---\ntype: mail\nraw: raw/emails/2026-01-01-x/thread.md\n---\n\n# Mail thread\n\nMAIL-ONLY-TOKEN [[hub]]\n",
    "mail-list.md": "---\ntype: mail\nraw: [raw/printed-docs/a.pdf, raw/emails/2026-01-01-x/thread.md]\n---\n\n# Mail two\n\nMAIL-LIST-TOKEN\n",
    "llm-chat.md": "---\ntype: ai-chat\nraw: raw/llm-chats/c.md\n---\n\n# LLM chat\n\nCHAT-VISIBLE-TOKEN [[hub]]\n",
    "jane.md": "---\ntype: person\n---\n\n# Jane\n\nPERSON-VISIBLE-TOKEN [[hub]]\n",
}


class PublicRulesTests(unittest.TestCase):
    """Public builds keep persons and LLM chats, and drop only distilled-think, scopes and email-derived pages."""

    @classmethod
    def setUpClass(cls):
        if not _have_git():
            raise unittest.SkipTest("git not available")
        cls.tmp = tempfile.mkdtemp(prefix="share-rules-")
        cls.repo = make_repo(cls.tmp, pages=MAIL_PAGES)
        res = build_from(cls.repo, os.path.join(cls.tmp, "out"), "public", label="public")
        cls.html = read_html(res)
        cls.data = kb_data(cls.html)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_email_derived_pages_are_dropped_everywhere(self):
        for tok in ("MAIL-ONLY-TOKEN", "MAIL-LIST-TOKEN", "raw/emails/"):
            self.assertNotIn(tok, self.html)
        d = self.data
        self.assertEqual({n["id"] for n in d["graph"]["nodes"]}, {"hub", "llm-chat", "jane"})
        self.assertEqual({c["id"] for c in d["index"]["pages"]}, {"hub", "llm-chat", "jane"})
        self.assertEqual(set(d["pages"]), {"hub", "llm-chat", "jane"})
        for l in d["graph"]["links"]:
            self.assertNotIn("mail", l["source"] + l["target"])
        self.assertEqual(d["graph"]["node_count"], 3)
        self.assertEqual(d["graph"]["link_count"], len(d["graph"]["links"]))

    def test_person_and_llm_chat_stay_public_and_audit_clean(self):
        self.assertIn("PERSON-VISIBLE-TOKEN", self.html)
        self.assertIn("CHAT-VISIBLE-TOKEN", self.html)
        self.assertEqual(sb.PUBLIC_EXCLUDE_TYPES, {"distilled-think", "scope"})
        from kb_distillery.publish.site import snapshots
        self.assertEqual(snapshots.scan(self.data)["flags"], [])
