#!/usr/bin/env python3
"""Tests for the private site's read-only Start, Health, Digestion and Lifecycle tabs and its GitHub
link (src/kb_distillery/share/build.py).

Builds the same synthetic vault as test_share_build (private + public) once per class and checks:
the private shell carries the four tabs, their documents and data; the public one carries none of
it; the embedded data has no local state or absolute paths; builds are byte-deterministic; and the
shim routes the dashboard's links and API calls to the shell / the embedded data (node harness).
The real-repo cases run only when git and the kb-* tags are available.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from kb_distillery.paths import vault_root
ROOT = vault_root()

from kb_distillery.share import build as sb
from tests.share.test_share_build import (_Fixture, _git, _have_git, _have_tags, _node, build_from,  # noqa: E402
                              kb_data, read_html, sha256)

PRIVATE_ONLY = ("tab-start", "tab-health", "tab-digestion", "tab-lifecycle", "kb-doc-start", "kb-doc-health",
                "kb-doc-digestion", "kb-doc-lifecycle", 'data-view="start"', 'data-view="health"',
                'data-view="digestion"', 'data-view="lifecycle"', 'id="kb-github"')
GITHUB_REMOTE = "git@github.com:acme/vault.git"
GITHUB_URL = "https://github.com/acme/vault"
LOCAL_STATE_KEYS = ("working", "nightly", "stale_worktrees", "unpushed", "server", "failures", "recent",
                    "active_ingest", "infra_branches")
ABS_PATH_MARKERS = ("/Users/", "OneDrive", "~/Library", "/var/folders", "/tmp/", "/private/")


def doc(html, view):
    m = re.search(rf'<script type="application/json" id="kb-doc-{view}">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def health_snapshot(html):
    page = doc(html, "health")
    m = re.search(r'<script id="snapshot" type="application/json">(.*?)</script>', page, re.S)
    return json.loads(m.group(1))


def walk_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)
    elif isinstance(obj, str):
        yield obj


class PrivateTabsTests(_Fixture):
    def test_shell_has_the_tabs_in_order(self):
        views = re.findall(r'<button type="button" data-view="(\w+)" role="tab">', self.html)
        self.assertEqual(views, ["start", "graph", "explore", "health", "digestion", "lifecycle", "snapshots"])
        self.assertEqual(re.findall(r'id="kb-doc-(\w+)"', self.html),
                         ["start", "graph", "explore", "health", "digestion", "lifecycle"])
        for view in ("start", "health", "digestion", "lifecycle"):
            self.assertIn(f'<section id="tab-{view}" hidden><iframe id="frame-{view}"', self.html)
        self.assertIn('<section id="tab-graph"><iframe', self.html)   # Graph is still the landing tab
        self.assertIn("start|graph|explore|health|digestion|lifecycle", self.html)   # hash router knows them
        self.assertIn("Chart.js v4.4.1", doc(self.html, "health"))

    def test_start_document(self):
        page = doc(self.html, "start")
        self.assertIn("<h1>Start here</h1>", page)
        self.assertIn('id="now"', page)                          # the "right now" strip, fed by /api/lifecycle
        self.assertIn('fetch("/api/lifecycle"', page)
        self.assertNotIn('href="/chat"', page)                   # the Chat link is stripped at build time
        self.assertNotIn(">Chat<", page)
        for href in ("/lifecycle", "/digestion", "/graph", "/explore", "/start"):
            self.assertIn(f'href="{href}"', page)               # cross-view links stay; the shim routes them
        self.assertIn(".st-places", page)                        # start.css inlined
        self.assertIn(".lc-chip", page)                          # lifecycle.css inlined
        self.assertNotIn("/static/start.css", page)

    def test_github_link(self):
        self.assertNotIn('id="kb-github"', self.html)            # the fixture has no remote → no link
        _git(self.repo, "remote", "add", "origin", GITHUB_REMOTE)
        try:
            private = build_from(self.repo, self.out, "private", label="github-private")
            public = build_from(self.repo, self.out, "public", label="github-public")
        finally:
            _git(self.repo, "remote", "remove", "origin")
        html = read_html(private)
        self.assertIn(f'<a id="kb-github" href="{GITHUB_URL}" target="_blank" rel="noopener"', html)
        self.assertIn("GitHub ↗</a>", html)
        nav = html[html.index('<nav class="kb-nav"'):html.index("</nav>")]
        self.assertLess(nav.index('id="kb-github"'), nav.index('id="kb-theme"'))   # beside the theme toggle
        self.assertEqual(kb_data(html)["lifecycle"]["github"], GITHUB_URL)
        pub = read_html(public)
        self.assertNotIn('id="kb-github"', pub)
        self.assertNotIn("acme/vault", pub)
        self.assertNotIn(GITHUB_URL, pub)

    def test_github_url_normaliser(self):
        for remote in ("git@github.com:acme/vault.git", "https://github.com/acme/vault.git",
                       "https://github.com/acme/vault", "ssh://git@github.com/acme/vault.git\n"):
            self.assertEqual(sb.github_url(remote), GITHUB_URL, remote)
        for remote in ("", None, "https://gitlab.com/acme/vault.git", "git@example.com:acme/vault.git"):
            self.assertIsNone(sb.github_url(remote), remote)

    def test_documents_are_inlined_and_shimmed(self):
        for view in ("start", "health", "digestion", "lifecycle"):
            page = doc(self.html, view)
            first = page.index("<script>")
            self.assertIn("kb-static.js", page[first:first + 400])
            self.assertNotIn("{{NAV}}", page)
            self.assertNotIn('class="app-nav"', page)          # the dashboard's nav bar is not embedded
            self.assertNotIn("<script src=", page)
            self.assertNotIn('<link rel="stylesheet" href=', page)
        health = doc(self.html, "health")
        self.assertIn('id="btn-refresh"', health)                # hidden by the shim
        self.assertIn('data-cluster="performance"', health)
        self.assertIn("window.Chart=", health)                   # vendored Chart.js inlined
        self.assertNotIn("cdn.jsdelivr.net/npm/chart.js", health)

    def test_health_snapshot_is_frozen(self):
        snap = health_snapshot(self.html)
        self.assertEqual(snap["generated_at"], "2026-01-02T03:04:05Z")
        for k in ("lint_ms", "sha1_ms", "wiki_ms", "links_ms"):
            self.assertEqual(snap["values"][k], 0)
        self.assertEqual(snap["graphs"]["lint_phases_ms"], {"sha1": 0, "wiki": 0, "links": 0})
        self.assertEqual(snap["values"]["hooks"], "n/a")
        self.assertEqual(snap["statuses"]["hooks"], "ok")
        self.assertNotIn("_rows", snap)
        self.assertEqual(snap["wiki_pages"], 4)
        self.assertIn("in_degree", snap["graphs"])

    def test_digestion_data(self):
        d = self.data["digestion"]
        self.assertEqual(d["generated_at"], "2026-01-02T03:04:05Z")
        for k in ("summary", "items", "inbox", "collections", "titles", "coherence", "distill_review", "shallow_papers"):
            self.assertIn(k, d)
        for k in ("server", "failures", "recent", "active_ingest"):
            self.assertNotIn(k, d)
        self.assertNotIn("active_ingest", d["summary"])
        self.assertEqual(d["distill_review"], [{"slug": "gamma", "proposals": 0}])   # no think/ source path
        self.assertEqual(d["shallow_papers"], [{"slug": "delta"}])
        for item in d["items"]:
            self.assertIsNone(item["age_days"])
            self.assertNotEqual(item["last_op"], "modified")

    def test_lifecycle_data(self):
        lc = self.data["lifecycle"]
        sha = self.private.manifest.content_sha
        self.assertEqual(lc["generated_at"], "2026-01-02T03:04:05Z")
        self.assertEqual(lc["branch"], "main")
        self.assertEqual(lc["head"], sha[:9])
        self.assertEqual(lc["version"], "0.1.1")
        from kb_distillery.core.schema import SCHEMA_VERSION
        self.assertEqual(lc["schema"]["version"], f"{SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]}")
        self.assertEqual([r["sha"] for r in lc["timeline"]], [sha])
        self.assertEqual(lc["timeline"][0]["op"], "import")
        self.assertEqual(lc["stats"], {"kb_steps": 1, "pr_merges": 0, "ops_30d": {"import": 1}, "undone": 0})
        self.assertEqual(lc["snapshots"], [])
        self.assertEqual(sorted(lc["policy"]), ["mode", "strict"])
        for k in LOCAL_STATE_KEYS:
            self.assertNotIn(k, lc)

    def test_lifecycle_snapshots_are_annotated_tags_on_the_history(self):
        _git(self.repo, "tag", "-a", "kb-0.1.1", "-m", "week 1")
        try:
            res = build_from(self.repo, self.out, "private", label="annotated")
        finally:
            _git(self.repo, "tag", "-d", "kb-0.1.1")
        lc = kb_data(read_html(res))["lifecycle"]
        self.assertEqual([(s["tag"], s["label"]) for s in lc["snapshots"]], [("kb-0.1.1", "week 1")])
        self.assertRegex(lc["snapshots"][0]["date"], r"^\d{4}-\d{2}-\d{2}$")   # the tag's creation date
        self.assertEqual(lc["timeline"][0]["snapshot_tag"], "kb-0.1.1")

    def test_private_data_has_no_local_state_or_paths(self):
        snaps = {"health": health_snapshot(self.html), "digestion": self.data["digestion"], "lifecycle": self.data["lifecycle"]}
        for name, snap in snaps.items():
            for s in walk_strings(snap):
                for marker in ABS_PATH_MARKERS:
                    self.assertNotIn(marker, s, f"{name}: {s!r}")
                self.assertFalse(s.startswith("think/"), f"{name}: {s!r}")
                self.assertNotIn("/think/", s, f"{name}: {s!r}")
            for k in LOCAL_STATE_KEYS:
                self.assertNotIn(k, snap, name)
        self.assertNotIn(self.repo, self.html)                     # the fixture's own absolute path
        self.assertNotIn(self.tmp, self.html)

    def test_public_has_none_of_it(self):
        html = self.pub_html
        for s in PRIVATE_ONLY:
            self.assertNotIn(s, html)
        self.assertNotIn("digestion", self.pub_data)
        self.assertNotIn("lifecycle", self.pub_data)
        self.assertEqual(re.findall(r'id="kb-doc-(\w+)"', html), ["graph", "explore"])
        self.assertEqual(re.findall(r'data-view="(\w+)"', html), ["graph", "explore"])
        self.assertNotIn("Start here", html)
        self.assertNotIn("GitHub ↗", html)
        self.assertNotIn("window.Chart=", html)
        self.assertNotIn('id="snapshot" type="application/json"', html)
        self.assertNotIn("Thesis Wiki Health", html)

    def test_shimmed_api_covers_the_new_pages(self):
        for route in ("/api/pipeline", "/api/lifecycle", "/api/health"):
            self.assertIn(route, sb.SHIMMED_API)
        for html in (self.html, self.pub_html):
            for m in re.finditer(r"(?<!/admin)(/api/[a-z/]+)", html):
                self.assertIn(m.group(1).rstrip("/"), sb.SHIMMED_API, m.group(0))

    def test_deterministic(self):
        again = build_from(self.repo, self.out, "private", label="again-tabs")
        self.assertEqual(again.manifest.sha256, self.private.manifest.sha256)
        self.assertEqual(sha256(again.dir / "index.html"), sha256(self.private.dir / "index.html"))


NODE_HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const [,, shimPath, dataPath] = process.argv;
const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const noop = () => {};
const listeners = {};
const posted = [];
const location = { href: "about:srcdoc", hash: "" };
const el = () => ({ style: {}, classList: { add: noop }, setAttribute: noop, replaceWith: noop, hidden: false, closest: () => null });
const ctx = {
  KB_DATA: null, console, URL, Response: class { constructor(b, i) { this.body = b; this.init = i; } },
  MutationObserver: class { observe() {} }, setTimeout, clearTimeout, location,
  document: { addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); }, readyState: "complete",
              getElementById: () => null, body: null, head: { appendChild: noop }, createElement: el,
              querySelectorAll: () => [], documentElement: { getAttribute: () => null } },
  matchMedia: () => ({ matches: false }),
  parent: { KB_DATA: data, postMessage: (m) => posted.push(m) },
};
ctx.window = ctx; ctx.addEventListener = noop;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(shimPath, "utf8"), ctx);
function click(href) {
  const prevented = { value: false };
  const a = { getAttribute: () => href };
  const e = { target: { closest: () => a }, preventDefault: () => { prevented.value = true; }, stopPropagation: noop };
  for (const fn of listeners.click || []) fn(e);
  return prevented.value;
}
const out = { clicks: {}, routes: {} };
for (const h of ["/lifecycle", "/digestion", "/pipeline", "/", "/index.html", "/graph", "/explore#/alpha", "/start", "/chat", "https://github.com/x/y/pull/1"]) {
  out.clicks[h] = click(h);
}
out.posted = posted;
out.location = location.href;
out.views = {};
for (const h of ["/start", "/chat"]) { const v = ctx.KB_STATIC.viewOf(h); out.views[h] = v ? v.view : null; }
for (const r of ["/api/pipeline", "/api/lifecycle", "/api/health", "/api/share/status"]) {
  const res = ctx.KB_STATIC.route(r);
  out.routes[r] = { status: (res.init && res.init.status) || 200, keys: Object.keys(JSON.parse(res.body) || {}).sort() };
}
process.stdout.write(JSON.stringify(out));
"""


def sb_view(got, href):
    """The view the shim resolved for `href` (None = no nav posted, i.e. a toast)."""
    return got["views"].get(href)


class ShimRoutingTests(_Fixture):
    """The shim intercepts the dashboard's cross-page links and answers the new API routes."""

    def _run(self, data):
        d = tempfile.mkdtemp(prefix="share-shim-", dir=self.tmp)
        data_path = os.path.join(d, "data.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        harness = os.path.join(d, "h.js")
        with open(harness, "w") as f:
            f.write(NODE_HARNESS)
        js = subprocess.run([_node(), harness, str(sb.SHIM_PATH), data_path], capture_output=True, text=True)
        self.assertEqual(js.returncode, 0, js.stderr)
        return json.loads(js.stdout)

    def setUp(self):
        if not _node():
            self.skipTest("node not available")

    def test_private_links_and_routes(self):
        got = self._run(self.data)
        clicks = got["clicks"]
        for href in ("/lifecycle", "/digestion", "/pipeline", "/", "/index.html", "/graph", "/explore#/alpha", "/start", "/chat"):
            self.assertTrue(clicks[href], href)                 # intercepted: the frame never navigates
        self.assertFalse(clicks["https://github.com/x/y/pull/1"])   # external links are the browser's
        self.assertEqual(got["location"], "about:srcdoc")
        navs = [(m["view"], m.get("hash"), m.get("focus")) for m in got["posted"] if m["type"] == "kb:nav"]
        self.assertEqual(navs, [("lifecycle", None, None), ("digestion", None, None), ("digestion", None, None),
                                ("health", None, None), ("health", None, None), ("graph", None, ""),
                                ("explore", "#/alpha", None), ("start", None, None)])   # /chat: a toast, no nav
        self.assertEqual(sb_view(got, "/chat"), None)
        routes = got["routes"]
        self.assertEqual(routes["/api/pipeline"]["status"], 200)
        self.assertIn("items", routes["/api/pipeline"]["keys"])
        self.assertEqual(routes["/api/lifecycle"]["status"], 200)
        self.assertIn("timeline", routes["/api/lifecycle"]["keys"])
        self.assertEqual(routes["/api/health"]["status"], 404)
        self.assertEqual(routes["/api/share/status"]["status"], 404)

    def test_public_data_answers_404(self):
        got = self._run(self.pub_data)
        self.assertEqual(got["routes"]["/api/pipeline"]["status"], 404)
        self.assertEqual(got["routes"]["/api/lifecycle"]["status"], 404)
        self.assertTrue(got["clicks"]["/lifecycle"])            # still intercepted: the shell falls back to graph


class RealRepoTabsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _have_tags():
            raise unittest.SkipTest("real kb-* tags not available")
        cls.tmp = tempfile.mkdtemp(prefix="share-real-tabs-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _build(self, ref, label):
        return sb.build(ref, root=ROOT, viewer_root=ROOT, viewer_worktree=True, out_root=self.tmp, label=label)

    def test_main_tabs_have_data(self):
        res = self._build("main", "main-tabs")
        html = read_html(res)
        self.assertLessEqual(len(html.encode("utf-8")), sb.MAX_HTML_BYTES)
        data = kb_data(html)
        lc, dg, hs = data["lifecycle"], data["digestion"], health_snapshot(html)
        self.assertEqual(lc["branch"], "main")
        self.assertEqual(lc["version"], res.manifest.kb_version)
        self.assertEqual(lc["generated_at"], res.manifest.built_at)
        self.assertTrue(lc["timeline"])
        self.assertEqual(lc["timeline"][0]["sha"], res.manifest.content_sha)
        self.assertTrue(lc["snapshots"])
        # the newest annotated snapshot on main is listed (older ones age out of the recent history shown)
        newest = next(line.split()[0] for line in _git(ROOT, "for-each-ref", "--sort=-creatordate", "--merged", "main",
                                                       "--format=%(refname:short) %(objecttype)", "refs/tags/kb-*").stdout.splitlines()
                      if line.split()[1] == "tag")
        self.assertIn(newest, [s["tag"] for s in lc["snapshots"]])
        self.assertTrue(lc["github"].startswith("https://github.com/"))
        self.assertIn(f'<a id="kb-github" href="{lc["github"]}" target="_blank" rel="noopener"', html)
        self.assertIn("<h1>Start here</h1>", doc(html, "start"))
        self.assertGreater(dg["summary"]["files"], 100)
        self.assertEqual(dg["summary"]["files"], len(dg["items"]))
        self.assertTrue(dg["collections"])
        self.assertGreater(hs["wiki_pages"], 100)
        self.assertEqual(hs["raw_files"], dg["summary"]["files"])    # the manifest, in both tabs
        self.assertEqual(hs["generated_at"], res.manifest.built_at)
        for snap in (lc, dg, hs):
            for s in walk_strings(snap):
                for marker in ABS_PATH_MARKERS:
                    self.assertNotIn(marker, s)
                self.assertFalse(s.startswith("think/"), s)
            for k in LOCAL_STATE_KEYS:
                self.assertNotIn(k, snap)
        self.assertNotIn(ROOT, html)

    def test_old_tag_builds_twice_identically(self):
        a = self._build("kb-0.9.6", "tag-a")
        b = self._build("kb-0.9.6", "tag-b")
        self.assertEqual(a.manifest.sha256, b.manifest.sha256)
        self.assertEqual(sha256(a.dir / "index.html"), sha256(b.dir / "index.html"))
        lc = kb_data(read_html(a))["lifecycle"]
        self.assertEqual(lc["version"], "0.9.6")
        self.assertEqual(lc["timeline"][0]["sha"], a.manifest.content_sha)
        self.assertEqual(lc["generated_at"], a.manifest.built_at)
        self.assertFalse(any(s["tag"] == "kb-0.10.5" for s in lc["snapshots"]))   # later history is not there


if __name__ == "__main__":
    unittest.main()
