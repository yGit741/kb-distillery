"""Pipeline harness: the real ingest path on a scratch fixture vault, LLM steps replaced by recordings.

    pixi run harness                     compare against the goldens (exit 1 + unified diff on mismatch)
    pixi run harness -- --update-goldens regenerate tests/fixtures/golden/
    pixi run harness -- --keep           leave the scratch vault on disk (path is printed)

Offline and deterministic: no network, no LLM. Every skipped step is logged as SKIPPED(reason) and
listed in the final report. Only CLI commands and pure builder functions are used (never private
helpers), so the runner survives the later meta/ -> backend/ move: update CODE_ROOT in
fixture_vault.py and the module names in the commands below, nothing else.
"""
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
from . import fixture_vault

FIXTURES = HERE.parent / "fixtures"
GOLDEN = FIXTURES / "golden"
RECORDED = FIXTURES / "recorded" / "digests.json"
PY = sys.executable

# order matters: the course hub and the series hub must exist (seeded) before their members land
CATALOG_PLAN = [   # (case, inbox name, extra catalog args)
    ("source-paper-local", "2020-local-fixture-paper.pdf", []),
    ("source-paper-arxiv-style", "2021-arxiv-style-fixture.pdf", []),
    ("source-ai-chat", "fixture-ai-chat.md", []),
    ("source-blog-post-hebrew", "fixture-hebrew-post.md", []),
    ("source-article-web-clip", "fixture-post-one.md",
     ["--collection", "series-fixture-kalai-blog", "--title", "Fixture post one"]),
    ("collection-book", "2019-fixture-book.pdf", []),
    ("collection-course-member-1", "rl-fixture-lecture-1.pdf",
     ["--collection", "course-fixture-rl", "--format", "presentations", "--title", "Lecture 1"]),
    ("collection-course-member-2", "rl-fixture-lecture-2.pdf",
     ["--collection", "course-fixture-rl", "--format", "presentations", "--title", "Lecture 2"]),
]
DIGEST_ORDER = ["source-paper-local", "source-paper-arxiv-style", "source-conversation-email",
                "source-ai-chat", "collection-book", "collection-course-member-1",
                "collection-course-member-2", "source-article-web-clip", "source-blog-post-hebrew"]

GRAPH_SNIPPET = r'''
import json, sys
from kb_distillery.services import chat as chat_data, pages as explore_data, graph as graph_data
snap = graph_data.build_graph_snapshot()
idx = explore_data.build_index()
for k in ("generated_at", "etag"):
    snap.pop(k, None)
idx.pop("generated_at", None)
for c in idx["pages"]:
    c.pop("mtime", None)
snap["nodes"] = sorted(snap["nodes"], key=lambda n: n["id"])
snap["links"] = sorted(snap["links"], key=lambda l: (l["source"], l["target"], l.get("kind", "")))
idx["pages"] = sorted(idx["pages"], key=lambda c: c["id"])
idx["links"] = sorted(idx["links"])
chat = {q: chat_data.retrieve(q) for q in ("noise stability", "generalization bound", "entropy")}
json.dump({"graph": snap, "index": idx, "chat_retrieval": chat}, open(sys.argv[1], "w"), sort_keys=True, ensure_ascii=False, indent=1)
'''


CHAT_SNIPPET = r'''
import sys
from kb_distillery.ingest.sources.chat import chat_build, chat_render
convs, _rows = chat_build.run(apply=True)          # clips -> meta/chats/ conversation trees
for conv in convs.values():
    page = chat_render.render(conv, sys.argv[1])
    open("wiki/chat-" + conv["slug"] + ".md", "w", encoding="utf-8").write(page)
'''


class StepFailed(Exception):
    pass


class Run:
    def __init__(self, work, mutate=None):
        self.work = Path(work)
        self.root = self.work / "vault"
        self.inputs = self.work / "inputs"
        self.mutate = mutate
        self.steps = []          # (name, status, seconds, detail)
        self.skips = []
        self.failures = []
        self.artifacts = {}      # relpath -> text, compared with goldens
        self.info = {}           # printed, never compared
        self.session_ids = {}
        self.email_raw = ""

    # ------------------------------------------------------------ plumbing
    def env(self, **extra):
        # the scratch vault is the knowledge base: no KB selection or CI mode leaks in from the caller
        e = {k: v for k, v in os.environ.items() if k not in ("KB_ROOT", "KB_CI", "KB", "KB_BASES_DIR")}
        e.update(PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0", NO_COLOR="1", KB_ROOT=str(self.root),
                 PYTHONPATH=str(self.root / "src"))     # the scratch vault runs its own copy of kb
        e.update(extra)
        return e

    def cmd(self, *args, expect=0, env=None, quiet=False):
        """Run one command with cwd = the scratch vault; return stdout+stderr. rc must equal `expect`."""
        p = subprocess.run([PY, *args], cwd=self.root, env=env or self.env(), capture_output=True, text=True, timeout=600)
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode != expect:
            raise StepFailed(f"`{' '.join(args)}` exited {p.returncode} (expected {expect})\n{out[-1500:]}")
        return out

    def ingest(self, *args, **kw):
        return self.cmd("-m", "kb_distillery.ingest", *args, **kw)

    def lint(self, expect=0):
        return self.cmd("-m", "kb_distillery.lint.lint", expect=expect)

    def step(self, name, fn):
        t0 = time.time()
        try:
            detail = fn()
            self.steps.append((name, "ok", time.time() - t0, detail or ""))
        except StepFailed as e:
            self.failures.append(f"{name}: {e}")
            self.steps.append((name, "FAILED", time.time() - t0, str(e).splitlines()[0]))
        except Exception as e:                                   # noqa: BLE001 - a harness bug is still a failure
            self.failures.append(f"{name}: {type(e).__name__}: {e}")
            self.steps.append((name, "FAILED", time.time() - t0, f"{type(e).__name__}: {e}"))

    def skip(self, name, reason):
        self.skips.append((name, reason))
        self.steps.append((name, f"SKIPPED({reason})", 0.0, ""))

    def pages(self):
        """The wiki's pages: index.md and log.md are the bundle's OKF reserved files, not pages."""
        return [p for p in (self.root / "wiki").glob("*.md") if p.name not in ("index.md", "log.md")]

    def wiki(self, slug):
        return self.root / "wiki" / f"{slug}.md"

    # ------------------------------------------------------------ steps
    def build(self):
        fixture_vault.build(self.root, self.inputs)
        if self.mutate:
            self.mutate(self.root)
        return f"{len(self.pages())} seed pages"

    def stage_and_catalog(self):
        for case, name, extra in CATALOG_PLAN:
            self.ingest("scrap", str(self.inputs / name))
            self.ingest("catalog", f"raw/inbox/{name}", *extra)
        out = self.ingest("scrap-mail", str(self.inputs / fixture_vault.CASES["source-conversation-email"]))
        m = re.search(r"→ (raw/inbox/mail-[^/\s]+)/", out)
        if not m:
            raise StepFailed(f"scrap-mail printed no thread folder: {out[-300:]}")
        self.ingest("catalog", m.group(1))
        self.email_raw = "raw/emails/" + m.group(1)[len("raw/inbox/mail-"):] + "/thread.md"
        left = sorted(os.listdir(self.root / "raw" / "inbox"))
        if left:
            raise StepFailed(f"inbox not drained: {left}")
        # dedup gate: staging the same bytes again must be refused
        self.ingest("scrap", str(self.inputs / "2020-local-fixture-paper.pdf"), expect=1)
        return f"{len(CATALOG_PLAN) + 1} sources cataloged, dedup gate holds"

    def recorded(self):
        return json.loads(RECORDED.read_text(encoding="utf-8"))

    def easy(self, case, rec):
        self.ingest("easy-digest", rec["raw"])
        page = next(p for p in self.pages()
                    if f"raw: {rec['raw']}" in p.read_text(encoding="utf-8") or rec["raw"] in p.read_text(encoding="utf-8").split("---")[1])
        text = page.read_text(encoding="utf-8")
        text = re.sub(r"^\*\*Problem:\*\*.*$", f"**Problem:** {rec['problem']}", text, count=1, flags=re.M)
        text = re.sub(r"^\*\*Main result:\*\*.*$", f"**Main result:** {rec['main']}", text, count=1, flags=re.M)
        if "**Problem:**" not in text:                # blog posts keep a summary section instead
            text = text.replace("## Blog Post Summary\n", f"## Blog Post Summary\n\n{rec['problem']} {rec['main']}\n", 1)
        page.write_text(text, encoding="utf-8")       # the recorded 'LLM' summary
        self.lint()

    def transactional(self, case, rec):
        begin = ["deep-digest", "--confirm-heavy"] if rec["depth"] == "deep" else ["full-digest"]
        target = rec.get("hub") or rec["raw"]
        scope = ["--row", rec["row"]] if rec.get("hub") else rec.get("scope", [])
        out = self.ingest(*begin[:1], target, *begin[1:], *scope)
        m = re.search(r"session (\S+) opened", out) or re.search(r"digest session (\S+)", out)
        if not m:
            raise StepFailed(f"no session id in: {out[-300:]}")
        sha = m.group(1)
        self.session_ids[case] = sha
        self.ingest("extract", sha)                      # writes the claims template + extracted.text
        claims = dict(rec["claims"], raw=rec["raw"])
        path = self.root / "meta" / ".ingest" / sha / "claims.json"
        path.write_text(json.dumps(claims, indent=2), encoding="utf-8")   # the recorded 'LLM' response
        self.ingest("extract", sha)                      # validates claims.json
        self.ingest("map", sha)
        self.ingest("draft", sha)
        self.ingest("finalize", sha)
        if rec.get("overview"):                          # 'write its ## Overview by hand'
            hub = next((self.root / "wiki").glob("book-*.md"))
            t = hub.read_text(encoding="utf-8")
            t = re.sub(r"## Overview\n\n<!--.*?-->", "## Overview\n\n" + rec["overview"], t, count=1, flags=re.S)
            hub.write_text(t, encoding="utf-8")

    def chat_pipeline(self, rec):
        """ai-chat pages are not digested by the transactional CLI (lint refuses them without a
        meta/chats tree): the chat pipeline builds the tree and renders the page. No CLI entry point,
        so its two public functions are called from a snippet."""
        snippet = self.work / "chat_snippet.py"
        snippet.write_text(CHAT_SNIPPET, encoding="utf-8")
        self.cmd(str(snippet), rec["title"])
        self.lint()

    def digests(self):
        recs = self.recorded()
        done = []
        for case in DIGEST_ORDER:
            rec = dict(recs[case])
            rec["raw"] = rec["raw"].replace("{email_thread}", self.email_raw)
            try:
                if rec["depth"] == "chat-pipeline":
                    self.chat_pipeline(rec)
                else:
                    (self.easy if rec["depth"] == "easy" else self.transactional)(case, rec)
            except StepFailed as e:
                raise StepFailed(f"[{case}] {e}")
            done.append(f"{case}:{rec['depth']}")
        return ", ".join(done)

    def final_lint(self):
        out = self.lint(expect=0)       # exit 0 == no lint errors
        self.artifacts["lint.txt"] = out
        m = re.search(r"(\d+) pages · (\d+) raw files · (\d+) queued · (\d+) errors · (\d+) warnings", out)
        return m.group(0) if m else "lint ran"

    def builders(self):
        snippet = self.work / "graph_snippet.py"        # kept outside the vault (an interpreter loads its cwd)
        snippet.write_text(GRAPH_SNIPPET, encoding="utf-8")
        out = self.work / "builders.json"
        self.cmd(str(snippet), str(out))
        data = json.loads(out.read_text(encoding="utf-8"))
        self.artifacts["graph.json"] = json.dumps(data["graph"], sort_keys=True, indent=1, ensure_ascii=False)
        self.artifacts["explorer-index.json"] = json.dumps(data["index"], sort_keys=True, indent=1, ensure_ascii=False)
        self.artifacts["chat-retrieval.json"] = json.dumps(data["chat_retrieval"], sort_keys=True, indent=1, ensure_ascii=False)
        return f"graph {data['graph']['node_count']} nodes / {data['graph']['link_count']} links"

    def share(self):
        out = self.work / "share" / "index.html"
        sha0 = "0" * 40
        template = self.work / "share" / "app-template.html"        # stands in for the built app's index.html
        template.parent.mkdir(parents=True, exist_ok=True)
        template.write_text("<!doctype html><html><head><title>app</title></head><body></body></html>\n", encoding="utf-8")
        text = self.cmd("-m", "kb_distillery.publish.site.build", "--inner", "--app-index", str(template),
                        "--out", str(out), "--profile", "public",
                        "--content-ref", "main", "--content-sha", sha0, "--kb-version", "0.0.0",
                        "--viewer-sha", sha0, "--built-at", "2026-01-01T00:00:00Z",
                        env=self.env(KB_ROOT=str(self.root)))
        m = re.search(r"\((\d+) nodes, (\d+) pages, (\d+) KB\)", text)
        if not m:
            raise StepFailed(f"unexpected share output: {text[-300:]}")
        self.artifacts["share-summary.json"] = json.dumps({"nodes": int(m.group(1)), "pages": int(m.group(2))}, indent=1)
        self.info["share_index_html_bytes"] = out.stat().st_size
        return f"{m.group(1)} nodes, {m.group(2)} pages, {out.stat().st_size // 1024} KB (size not compared)"

    def nightly(self):
        out = self.cmd("-m", "kb_distillery.ops.nightly_report", "--root", str(self.root), "--json")
        doc = json.loads(out[out.index("{"):])
        digest = {"title": doc["title"], "status": doc["status"], "headline": doc["headline"],
                  "sections": [s["id"] or s["title"] for s in doc["sections"]]}
        self.artifacts["nightly-report.json"] = json.dumps(digest, sort_keys=True, indent=1)
        return doc["headline"]

    # ------------------------------------------------------------ goldens
    def collect(self):
        r = self.root
        for p in sorted((r / "wiki").glob("*.md")):
            if p.name in ("index.md", "log.md"):        # OKF reserved files: their own artifacts below
                continue
            self.artifacts[f"wiki/{p.name}"] = p.read_text(encoding="utf-8")
        self.artifacts["index.md"] = (r / "wiki" / "index.md").read_text(encoding="utf-8")
        rows = []
        for line in (r / "meta" / "corpus.tsv").read_text(encoding="utf-8").splitlines():
            cols = line.split("\t")
            if len(cols) > 2 and cols[0].endswith(".pdf"):
                cols[1] = "<pdf-sha1>"               # a PDF library may embed a random /ID: PDF bytes differ per run
            rows.append("\t".join(cols))
        self.artifacts["corpus.tsv"] = "\n".join(rows) + "\n"
        self.artifacts["coherence-warnings.tsv"] = (r / "meta" / "coherence-warnings.tsv").read_text(encoding="utf-8")
        self.artifacts["meta-chats-index.json"] = (r / "meta" / "chats" / "index.json").read_text(encoding="utf-8")
        self.artifacts["log.md"] = (r / "wiki" / "log.md").read_text(encoding="utf-8")
        steps = [f"{n}: {s}" for n, s, _t, _d in self.steps if n != "collect goldens"]
        self.artifacts["steps.txt"] = "\n".join(steps) + "\n"

    def normalise(self, rel, text):
        for p in {str(self.root), str(self.root.resolve()), str(self.inputs), str(self.inputs.resolve()),
                  str(self.work), str(self.work.resolve())}:
            text = text.replace(p, "<scratch>")
        if not rel.startswith("wiki/"):
            text = re.sub(r"\b[0-9a-f]{12}\b", "<sha12>", text) if rel in ("lint.txt", "log.md") else text
        text = re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", "<ts>", text)
        if rel == "log.md":
            text = re.sub(r"^## \d{4}-\d\d-\d\d$", "## <date>", text, flags=re.M)
        return text

    def compare(self, update):
        got = {rel: self.normalise(rel, t) for rel, t in self.artifacts.items()}
        if update:
            if GOLDEN.exists():
                shutil.rmtree(GOLDEN)
            for rel, t in got.items():
                dest = GOLDEN / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(t, encoding="utf-8")
            return [], len(got)
        want = {str(p.relative_to(GOLDEN)): p.read_text(encoding="utf-8") for p in GOLDEN.rglob("*") if p.is_file()}
        diffs = []
        for rel in sorted(set(want) | set(got)):
            a, b = want.get(rel), got.get(rel)
            if a == b:
                continue
            if a is None:
                diffs.append(f"+++ new artifact not in goldens: {rel}")
            elif b is None:
                diffs.append(f"--- golden artifact no longer produced: {rel}")
            else:
                diffs.append("".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                                          f"golden/{rel}", f"actual/{rel}", n=2)))
        return diffs, len(got)


def run(update=False, keep=False, workdir=None, mutate=None, quiet=False):
    """Run the whole pipeline; returns (exit_code, Run). Importable by the bite test."""
    work = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="kb-harness-"))
    work.mkdir(parents=True, exist_ok=True)
    h = Run(work, mutate=mutate)
    t0 = time.time()
    h.step("build fixture vault", h.build)
    if not h.failures:
        h.step("stage + catalog (scrap -> catalog, dedup gate)", h.stage_and_catalog)
        h.step("digests (easy / full / deep, recorded LLM)", h.digests)
        h.step("lint (structural + coherence)", h.final_lint)
        h.step("graph + explorer + chat-retrieval builders", h.builders)
        h.step("share build (inner, public profile)", h.share)
        h.step("nightly report preview", h.nightly)
    h.skip("scrap by URL / arXiv id + arXiv metadata lookup", "network")
    h.skip("scrap-wordpress / scrap-gdrive / scrap-mail --imap-thread / researcher index", "network")
    h.skip("video ingest", "no ingest path: video pages are hand-authored (seeded page covers lint/graph/share)")
    h.skip("share outer build, deploy, snapshots, rollback", "needs a git ref of the scratch vault and Cloudflare")
    h.skip("chat answer (agent / Messages API)", "LLM + network; retrieval index is covered")
    h.skip("dashboard HTTP server", "builders are called as pure functions instead")
    diffs = []
    n_artifacts = 0
    if not h.failures:
        h.step("collect goldens", h.collect)
        diffs, n_artifacts = h.compare(update)
    elapsed = time.time() - t0
    if not quiet:
        report(h, diffs, n_artifacts, update, elapsed, work)
    if not keep and not workdir:
        shutil.rmtree(work, ignore_errors=True)
    code = 1 if (h.failures or diffs) else 0
    return code, h


def report(h, diffs, n, update, elapsed, work):
    print("pipeline harness")
    for name, status, secs, detail in h.steps:
        print(f"  [{status}] {name}" + (f"  ({secs:.1f}s)" if secs else "") + (f" - {detail}" if detail and status == 'ok' else ""))
    if h.skips:
        print(f"\nSKIPPED steps ({len(h.skips)}):")
        for name, reason in h.skips:
            print(f"  - {name}: {reason}")
    if h.info:
        print("\ninfo (not compared): " + ", ".join(f"{k}={v}" for k, v in h.info.items()))
    for f in h.failures:
        print(f"\nFAILURE {f}")
    if update and not h.failures:
        print(f"\ngoldens regenerated: {n} artifacts under {GOLDEN}")
    elif diffs:
        print(f"\nGOLDEN MISMATCH in {len(diffs)} artifact(s):\n")
        print("\n".join(diffs))
    elif not h.failures:
        print(f"\nOK - {n} artifacts match the goldens ({elapsed:.0f}s)")
    if h.failures or diffs:
        print(f"\nHARNESS FAILED ({elapsed:.0f}s); scratch vault: {work}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update-goldens", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the scratch vault and print its path")
    ap.add_argument("--workdir", default=None)
    a = ap.parse_args(argv)
    code, h = run(update=a.update_goldens, keep=a.keep, workdir=a.workdir)
    if a.keep and not a.workdir:
        print(f"scratch vault kept: {h.work}")
    return code


if __name__ == "__main__":
    sys.exit(main())
