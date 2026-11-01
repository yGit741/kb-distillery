#!/usr/bin/env python3
"""End-to-end pipeline test: a tiny vault through the real entry points, offline, deterministic.

The vault is built in a temp dir from `tests/testdata/e2e/` (seed pages + inbox items); its `meta/`
holds symlinks to this checkout's code, so every CLI runs exactly as in the real vault
(`python -m kb_distillery.ingest …` with cwd = the temp vault, ROOT resolved from the symlinked paths) and
writes only into the temp vault. Commits are off (`KB_OPS_DISABLE=1`), arXiv is never asked
(no `arxiv-*` inbox names), and the only LLM boundary — the agent filling `claims.json` and the
easy-digest summary lines — is replaced by the recorded files in `testdata/e2e/claims/`.

Steps: catalog (paper, book, web clip, blog post, slide deck into a course, clip into a series,
mail thread) → easy-digest (paper, article, series member, mail) → full-digest begin →
extract → map → draft → finalize (paper, course row → lecture, book pages → part) → lint →
coherence status → graph / explore / digestion / corpus builders → share data + a public build.

Goldens live in `tests/testdata/e2e/golden/`; regenerate them with `KB_UPDATE_GOLDEN=1` and review
the diff — a schema migration may change front matter and dispositions only.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from kb_distillery.kbconfig import checkout_root
from kb_distillery.paths import CODE_DIR, vault_root
CHECKOUT_ROOT = checkout_root()
META = os.path.join(vault_root(), "meta")
REPO = vault_root()
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "testdata", "e2e")
GOLDEN = os.path.join(DATA, "golden")
# meta/ entries that are data, not code: the temp vault gets its own (or none)
NOT_CODE = {"corpus.tsv", "log.md", "coherence-warnings.tsv", "aliases.tsv", "chats", "testdata",
            "migration", "raw-renames.tsv", "__pycache__", "thesis.md"}
GOLDEN_AREAS = ("statistics", "boolean-analysis", "fourier-analysis", "optimization-theory", "learning-theory",
                "info-theory", "implicit-regularization", "tensor-factorization", "complex-nn", "quantum")
BUILT_AT = "2026-01-01T00:00:00Z"
FIXED_NOW = 1767225600       # 2026-01-01, for mtimes the builders read


def _pdf(path, text, pages=1):
    import fitz  # pymupdf, a pixi dependency
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        base = text if i == 0 else f"Page {i + 1}. " + " ".join(text.split())
        body = (base + "\n") * (1 + 300 // max(1, len(base)))      # a typed text layer, not ink
        page.insert_textbox(fitz.Rect(72, 72, 540, 760), body, fontsize=10)
    doc.set_metadata({"creationDate": "D:20260101000000", "modDate": "D:20260101000000",
                      "producer": "e2e", "creator": "e2e"})
    doc.save(path, garbage=4, deflate=True, no_new_id=True)
    doc.close()


def build_vault(root):
    os.makedirs(os.path.join(root, "meta"))
    # vault-side inputs the tools read: templates from the base kit's defaults/, ops config from the vault's meta/
    os.symlink(os.path.join(CHECKOUT_ROOT, "src", "kb_distillery", "kits", "base", "defaults", "templates"), os.path.join(root, "meta", "templates"))
    if os.path.isdir(os.path.join(META, "ops")):
        os.symlink(os.path.join(META, "ops"), os.path.join(root, "meta", "ops"))
    os.makedirs(os.path.join(root, "src"))
    os.symlink(CODE_DIR, os.path.join(root, "src", "kb_distillery"))     # the checkout's code
    shutil.copytree(os.path.join(DATA, "seed", "wiki"), os.path.join(root, "wiki"))
    # the fixture is a knowledge base of its own with the default types; its areas are pinned to the thesis set the
    # goldens were recorded with, so the test gives the same answer whichever kb the suite runs under
    areas = sorted(GOLDEN_AREAS)
    with open(os.path.join(root, "kb.toml"), "w", encoding="utf-8") as f:
        f.write('[kb]\nid = "e2e"\nname = "E2E fixture vault"\nschema_version = "1.4"\n\n[types]\nareas = ['
                + ", ".join(f'"{a}"' for a in areas) + "]\n")
    for name in os.listdir(os.path.join(DATA, "seed", "meta")):
        shutil.copy(os.path.join(DATA, "seed", "meta", name), os.path.join(root, "meta", name))
    inbox = os.path.join(root, "raw", "inbox")
    os.makedirs(inbox)
    for name in sorted(os.listdir(os.path.join(DATA, "inbox"))):
        src = os.path.join(DATA, "inbox", name)
        if name.endswith(".txt"):
            with open(src, encoding="utf-8") as f:
                text = f.read()
            _pdf(os.path.join(inbox, name[:-4] + ".pdf"), text, pages=61 if "book" in name else 1)
        elif os.path.isdir(src):
            shutil.copytree(src, os.path.join(inbox, name))
        else:
            shutil.copy(src, os.path.join(inbox, name))
    for d in ("raw/printed-docs", "raw/presentations", "raw/web-clips", "raw/emails", "think"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            if not os.path.islink(p):
                os.utime(p, (FIXED_NOW, FIXED_NOW))


class Pipeline:
    """Runs the real CLIs inside the temp vault and records a transcript of their exit codes."""

    def __init__(self, root):
        self.root = root
        self.env = {**{k: v for k, v in os.environ.items() if not k.startswith("KB_") and k != "KB"},
                    "KB_ROOT": root,       # the temp vault is the kb (the code symlinked into it no longer finds it by itself)
                    "KB_OPS_DISABLE": "1", "KB_NO_PUSH": "1", "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONHASHSEED": "0", "TZ": "UTC", "NO_PROXY": "*",
                    "PYTHONPATH": os.path.join(root, "src")}
        self.log = []

    def run(self, *args, ok=True, module=True):
        cmd = [sys.executable, "-m", *args] if module else [sys.executable, *args]
        cp = subprocess.run(cmd, cwd=self.root, env=self.env, capture_output=True, text=True, timeout=120)
        self.log.append((" ".join(args), cp.returncode))
        if ok and cp.returncode != 0:
            raise AssertionError(f"{' '.join(args)} → {cp.returncode}\n{cp.stdout[-3000:]}\n{cp.stderr[-3000:]}")
        return cp

    def ingest(self, *args, ok=True):
        return self.run("kb_distillery.ingest", *args, ok=ok)

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def write(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def session_for(self, raw):
        idir = os.path.join(self.root, "meta", ".ingest")
        for name in sorted(os.listdir(idir)):
            sp = os.path.join(idir, name, "session.json")
            if os.path.isfile(sp):
                with open(sp, encoding="utf-8") as f:
                    s = json.load(f)
                if s.get("status") == "open" and s.get("raw") == raw:
                    return name
        raise AssertionError(f"no open session for {raw}")

    def summarize(self, slug, problem, result):
        """The easy-digest agent step: fill the Problem / Main result lines."""
        rel = f"wiki/{slug}.md"
        text = self.read(rel)
        text = re.sub(r"^\*\*Problem:\*\*.*$", f"**Problem:** {problem}", text, count=1, flags=re.M)
        text = re.sub(r"^\*\*Main result:\*\*.*$", f"**Main result:** {result}", text, count=1, flags=re.M)
        self.write(rel, text)

    def full_digest(self, claims_name, *begin_args, raw=None):
        self.ingest(*begin_args)
        with open(os.path.join(DATA, "claims", f"{claims_name}.json"), encoding="utf-8") as f:
            claims = json.load(f)
        sha = self.session_for(raw or claims["raw"])
        self.ingest("extract", sha)
        self.write(f"meta/.ingest/{sha}/claims.json", json.dumps(claims, indent=2, ensure_ascii=False) + "\n")
        self.ingest("extract", sha)
        self.ingest("map", sha)
        self.ingest("draft", sha)
        self.ingest("finalize", sha)
        return sha


def run_pipeline(root):
    p = Pipeline(root)
    # --- catalog
    p.ingest("catalog", "raw/inbox/2024-tiny-rank-paper.pdf")
    p.ingest("catalog", "raw/inbox/2023-easy-skim-paper.pdf")
    p.ingest("catalog", "raw/inbox/2020-tiny-book.pdf")
    p.ingest("catalog", "raw/inbox/clip-why-rank-matters.md")
    p.ingest("catalog", "raw/inbox/blog-post.md")
    p.ingest("catalog", "raw/inbox/slides-intro.pdf", "--collection", "course-test-ml",
             "--format", "presentations", "--title", "Lecture 1 · Introduction")
    p.ingest("catalog", "raw/inbox/post-one.md", "--collection", "series-test-blog")
    p.ingest("catalog", "raw/inbox/mail-2026-01-02-rank-thread")
    # --- easy-digest (+ the agent's two summary lines)
    p.ingest("easy-digest", "paper-2023-easy-skim-paper")
    p.summarize("paper-2023-easy-skim-paper", "Is matrix completion biased to low rank?", "Yes, in a toy model.")
    p.ingest("easy-digest", "raw/web-clips/clip-why-rank-matters.md")
    p.summarize("article-clip-why-rank-matters", "Is low rank a good bias?", "The article argues it is.")
    p.ingest("easy-digest", "raw/web-clips/tblog-post-one.md")
    p.summarize("article-tblog-post-one", "Where does rank show up?", "Everywhere, says the post.")
    p.ingest("easy-digest", "raw/emails/2026-01-02-rank-thread/thread.md")
    # --- full-digest: a paper, a course row (→ lecture), a book section (→ part)
    p.full_digest("paper", "full-digest", "raw/printed-docs/2024-tiny-rank-paper.pdf")
    p.full_digest("lecture", "full-digest", "course-test-ml", "--row", "1",
                  raw="raw/presentations/tml-slides-intro.pdf")
    p.full_digest("part", "full-digest", "raw/printed-docs/2020-tiny-book.pdf", "--pages", "1-10")
    # --- checks
    lint = p.run("src/kb_distillery/lint/lint.py", module=False, ok=False)
    coherence = p.run("src/kb_distillery/core/coherence.py", "status", module=False, ok=False)
    return p, lint, coherence


_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")
_DATE_HDR = re.compile(r"^## \[\d{4}-\d{2}-\d{2}\]", re.M)


def _norm(obj, root):
    """Volatile values out: absolute temp paths, timestamps, mtimes, durations."""
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1, default=str)
    text = text.replace(root, "<vault>").replace(os.path.realpath(root), "<vault>")
    text = _TS.sub("<ts>", text)
    return json.loads(text)


VOLATILE_KEYS = {"generated_at", "mtime", "age_days", "updated", "lint_ms", "sha1_ms", "wiki_ms",
                 "links_ms", "duration_ms", "etag", "cataloged_at", "last_op", "ts", "server",
                 "code_mtime", "built_at", "age", "ago", "age_hours"}


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


BUILDERS = r"""
import json, sys
from kb_distillery.services import graph as graph_data, pages as explore_data, pipeline as digestion_data, corpus as corpus_data
out = {"graph": graph_data.build_graph_snapshot(), "explore": explore_data.build_index(),
       "digestion": digestion_data.build_digestion_snapshot()}
out["corpus"] = {f: corpus_data.build_corpus(f) for f in corpus_data.FORMATS}
from kb_distillery.share import build as sb
from pathlib import Path
out["share"] = sb.collect_data(Path("meta").resolve(), "%s", "0" * 40)
print(json.dumps(out, ensure_ascii=False, default=str))
""" % BUILT_AT


def collect_outputs(p, lint, coherence):
    root = p.root
    cp = p.run("-c", BUILDERS, module=False)
    data = json.loads(cp.stdout.strip().splitlines()[-1])
    share_out = os.path.join(root, ".share", "index.html")
    p.run("kb_distillery.share.build", "--inner", "--content-ref", "e2e", "--content-sha", "0" * 40,
          "--kb-version", "0.0.0", "--viewer-sha", "0" * 40, "--profile", "public",
          "--built-at", BUILT_AT, "--out", share_out)
    graph = data["graph"]
    outputs = {
        "transcript": p.log,
        "lint": [l for l in lint.stdout.splitlines() if l.startswith(("ERROR", "warn"))] + [f"rc={lint.returncode}"],
        "coherence": coherence.stdout.splitlines()[-5:] if coherence.stdout else [],
        "graph_nodes": sorted(({k: n.get(k) for k in ("id", "type", "layer", "group", "status", "depth",
                                                        "digestion_status") if k in n}
                               for n in graph.get("nodes", [])), key=lambda n: n["id"]),
        "graph_links": sorted(f"{l.get('source')}->{l.get('target')}:{l.get('kind', '')}" for l in graph.get("links", [])),
        "explore": _strip(data["explore"]),
        "digestion": _strip(data["digestion"]),
        "corpus_view": _strip(data["corpus"]),
        "share_data": _strip(data["share"]),
        "share_html_ok": os.path.getsize(share_out) > 10_000,
    }
    files = {}
    for d in ("wiki",):
        for fn in sorted(os.listdir(os.path.join(root, d))):
            files[f"{d}/{fn}"] = p.read(f"{d}/{fn}")
    files["meta/corpus.tsv"] = p.read("meta/corpus.tsv")
    files["index.md"] = p.read("index.md")
    files["meta/log.md"] = _DATE_HDR.sub("## [<date>]", p.read("meta/log.md"))
    return _norm(outputs, root), files


def _golden_paths():
    out = {}
    for dirpath, _d, fns in os.walk(GOLDEN):
        for fn in fns:
            full = os.path.join(dirpath, fn)
            out[os.path.relpath(full, GOLDEN)] = full
    return out


def write_golden(outputs, files):
    if os.path.isdir(GOLDEN):
        shutil.rmtree(GOLDEN)
    for rel, text in files.items():
        path = os.path.join(GOLDEN, "files", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    for key, val in outputs.items():
        with open(os.path.join(GOLDEN, f"{key}.json"), "w", encoding="utf-8") as f:
            json.dump(val, f, indent=1, sort_keys=True, ensure_ascii=False)
            f.write("\n")


class PipelineE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kb-e2e-")
        cls.addClassCleanup(lambda: os.environ.get("KB_E2E_KEEP") == "1" or shutil.rmtree(cls.tmp, ignore_errors=True))
        t0 = time.monotonic()
        build_vault(cls.tmp)
        cls.p, lint, coherence = run_pipeline(cls.tmp)
        cls.outputs, cls.files = collect_outputs(cls.p, lint, coherence)
        cls.seconds = time.monotonic() - t0
        if os.environ.get("KB_UPDATE_GOLDEN") == "1":
            write_golden(cls.outputs, cls.files)

    def test_fast_and_offline(self):
        self.assertLess(self.seconds, 60, f"e2e took {self.seconds:.0f}s")

    def test_lint_clean(self):
        self.assertEqual(self.outputs["lint"][-1], "rc=0", "\n".join(self.outputs["lint"]))
        self.assertFalse([l for l in self.outputs["lint"] if l.startswith("ERROR")])

    def test_my_notes_survive(self):
        self.assertIn("Hand-written note that no tool may overwrite", self.files["wiki/tensor-rank.md"])
        self.assertTrue(self.files["wiki/tensor-rank.md"].rstrip().endswith(
            "compare with matrix rank before the meeting."))

    def test_every_step_produced_its_page(self):
        for slug in ("paper-2024-tiny-rank-paper", "paper-2023-easy-skim-paper", "article-clip-why-rank-matters",
                     "article-tblog-post-one", "lecture-tml-slides-intro", "video-tiny-talk"):
            self.assertIn(f"wiki/{slug}.md", self.files, slug)
        self.assertTrue(any(k.startswith("wiki/part-2020-tiny-book") for k in self.files))
        self.assertTrue(any(k.startswith("wiki/mail-") for k in self.files))
        self.assertTrue(any(k.startswith("wiki/blog-") for k in self.files))
        self.assertIn("wiki/book-2020-tiny-book.md", self.files)
        self.assertTrue(self.outputs["share_html_ok"])

    def test_matches_golden(self):
        if os.environ.get("KB_UPDATE_GOLDEN") == "1":
            self.skipTest("goldens regenerated")
        golden = _golden_paths()
        self.assertTrue(golden, "no goldens — run with KB_UPDATE_GOLDEN=1")
        seen = set()
        for rel, text in self.files.items():
            key = os.path.join("files", rel)
            seen.add(key)
            self.assertIn(key, golden, f"new file {rel}")
            with open(golden[key], encoding="utf-8") as f:
                self.assertEqual(text, f.read(), f"{rel} differs from its golden")
        for key, val in self.outputs.items():
            gk = f"{key}.json"
            seen.add(gk)
            with open(golden[gk], encoding="utf-8") as f:
                self.assertEqual(json.loads(json.dumps(val, ensure_ascii=False)), json.load(f), f"{key} differs")
        self.assertEqual(sorted(set(golden) - seen), [], "golden files no longer produced")


if __name__ == "__main__":
    unittest.main()
