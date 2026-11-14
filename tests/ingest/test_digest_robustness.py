#!/usr/bin/env python3
"""Robustness of the full/deep-digest session pipeline (polarity heuristic, rollback, themes,
commit target, stale sessions, book gate, coherence CLI, theme slugs in claims)."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.vault import coherence
from kb_distillery.vault.graph import polarity_clash
from kb_distillery.ingest.sources.books import book
from kb_distillery.ingest import map as map_mod, paths, session
from kb_distillery.ops import wrap


class TestPolarity(unittest.TestCase):
    def test_real_negation_on_shared_topic_still_clashes(self):
        a = "Tensor rank always explains generalization in deep networks"
        b = "Tensor rank does not explain generalization in deep networks"
        self.assertTrue(polarity_clash(a, b)[0])

    def test_unlikely_to_almost_certain_vs_stub(self):
        a = "Under the assumption the probability of success goes from unlikely to almost certain."
        b = "Stub for success probability and the assumption of width."
        self.assertFalse(polarity_clash(a, b)[0])

    def test_saturated_regime_not_standard_attention_vs_self_attention(self):
        a = "We study the saturated regime, not standard attention, where softmax saturates."
        b = "Self-attention mixes tokens with softmax weights. Attention is a core transformer layer."
        self.assertTrue(polarity_clash(a, b)[0])                       # lexically alike ...
        self.assertFalse(polarity_clash(a, b, ignore=["self", "attention"])[0])   # ... but only the title word

    def test_distant_negation_does_not_count(self):
        a = ("Tensor rank explains generalization of deep networks in many cases and we also show "
             "extra material here and then; the proof does not use induction.")
        b = "Tensor rank explains generalization of deep networks."
        self.assertFalse(polarity_clash(a, b)[0])

    def test_lexical_clash_capped_below_error(self):
        def page(slug, body, link=""):
            text = f"---\ntype: paper\nmaturity: digested\n---\n\n# {slug}\n\n**Main result:** {body}\n\n{link}\n"
            return (f"wiki/{slug}.md", {"type": "paper", "maturity": "digested"}, text)
        pages = {
            "paper-a": page("paper-a", "tensor rank low rank factorization deep network generalization bound "
                            "implicit regularization gradient flow matrix completion always holds", "[[paper-b]]"),
            "paper-b": page("paper-b", "tensor rank low rank factorization deep network generalization bound "
                            "implicit regularization gradient flow matrix completion does not hold"),
        }
        with patch.object(coherence, "load_warnings", lambda: {}):
            hits = coherence.check_coherence(pages, rows={})
        self.assertTrue(hits)
        self.assertTrue(all(h["score"] < coherence.INTERNAL_ERROR_THRESHOLD for h in hits))

    def test_fresh_pages_do_not_clash_with_each_other(self):
        a = "wiki/p.md", {"type": "paper", "maturity": "digested"}, \
            "---\ntype: paper\n---\n\n**Main result:** tensor rank explains generalization deep networks\n\n[[stub]]\n"
        b = "wiki/stub.md", {"type": "idea"}, \
            "---\ntype: idea\n---\n\n## One-liner\n\ntensor rank does not explain generalization deep networks\n"
        pages = {"p": a, "stub": b}
        with patch.object(coherence, "load_warnings", lambda: {}):
            self.assertTrue(coherence.check_coherence(pages, rows={}))
            self.assertEqual(coherence.check_coherence(pages, rows={}, fresh={"p", "stub"}), [])


class Vault(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        for d in ("wiki", "raw/printed-docs", "meta"):
            os.makedirs(os.path.join(self.root, d))
        for mod, name, val in (
            (session, "ROOT", self.root), (map_mod, "ROOT", self.root), (paths, "ROOT", self.root),
            (paths, "INGEST_ROOT", os.path.join(self.root, "meta", ".ingest")),
            (session, "verify_raw", lambda r: r), (session, "sha1_file", lambda r: "abc123"),
            (session, "existing_digest_for_raw", lambda r, p=None: None),
        ):
            p = patch.object(mod, name, val)
            p.start()
            self.addCleanup(p.stop)
        self.raw = "raw/printed-docs/2024-x.pdf"

    def w(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def r(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, rel))


class TestRollback(Vault):
    def test_staging_kept_and_stubs_deleted_and_theme_restored(self):
        theme = "---\ntype: topic\n---\n\n## Papers\n\n- [[old]]\n"
        self.w("wiki/theme-learning-theory.md", theme)
        sha = session.begin(self.raw)
        sdir = paths.session_dir(sha)
        sess = paths.load_session(sha)
        sess["new_files"] = ["wiki/paper-x.md"]
        paths.save_session(sha, sess)
        plan = {"wiki_slug": "paper-x", "type": "paper",
                "moc_updates": [{"moc": "theme-learning-theory", "section": "Papers", "link": "paper-x"}]}
        self.w(f"meta/.ingest/{sha}/plan.json", json.dumps(plan))
        for name in ("paper-x", "my-concept", "q-my-question"):
            self.w(f"meta/.ingest/{sha}/staging/{name}.md", f"# {name}\n")
        with patch.object(session, "validate_plan", lambda p: None), \
                patch.object(session, "_record_book_part", lambda *a: None), \
                patch.object(session, "_record_hub_row", lambda *a: None), \
                patch.object(session.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            run.return_value.stderr = ""
            rc = session.finalize(sha)
        self.assertEqual(rc, 1)
        self.assertEqual(self.r("wiki/theme-learning-theory.md"), theme)       # (a)
        for name in ("paper-x", "my-concept", "q-my-question"):               # (b)
            self.assertFalse(self.exists(f"wiki/{name}.md"), name)
        kept = [d for d in os.listdir(sdir) if d.startswith("staging-aborted-")]   # (c)
        self.assertEqual(len(kept), 1)
        self.assertTrue(os.path.isfile(os.path.join(sdir, kept[0], "my-concept.md")))
        self.assertEqual(os.listdir(os.path.join(sdir, "staging")), [])

    def test_existing_page_overwritten_by_stage_is_restored(self):
        self.w("wiki/concept-a.md", "original\n")
        sha = session.begin(self.raw)
        self.w(f"meta/.ingest/{sha}/plan.json", json.dumps({"wiki_slug": "p", "type": "paper"}))
        self.w(f"meta/.ingest/{sha}/staging/concept-a.md", "replaced\n")
        with patch.object(session, "validate_plan", lambda p: None), \
                patch.object(session, "_record_book_part", lambda *a: None), \
                patch.object(session, "_record_hub_row", lambda *a: None), \
                patch.object(session.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = run.return_value.stderr = ""
            session.finalize(sha)
        self.assertEqual(self.r("wiki/concept-a.md"), "original\n")

    def test_map_registers_stubs(self):
        sha = session.begin(self.raw)
        claims = {"raw": self.raw, "concepts": ["new concept"], "open_questions": ["Why is x?"]}
        self.w(f"meta/.ingest/{sha}/claims.json", json.dumps(claims))
        with patch.object(map_mod, "validate_claims", lambda c: None), \
                patch.object(map_mod, "wiki_slugs", lambda: set()), \
                patch.object(map_mod, "person_from_raw", lambda r: None):
            map_mod.run_map(sha)
        nf = paths.load_session(sha)["new_files"]
        self.assertIn("wiki/new-concept.md", nf)
        self.assertIn("wiki/q-why-is-x.md", nf)

    def test_begin_after_abort_restores_claims_and_plan_and_archives(self):
        sha = session.begin(self.raw)
        self.w(f"meta/.ingest/{sha}/claims.json", '{"a": 1}')
        self.w(f"meta/.ingest/{sha}/plan.json", '{"b": 2}')
        self.w(f"meta/.ingest/{sha}/staging/draft.md", "x")
        session.abort(sha)
        sha2 = session.begin(self.raw)
        self.assertEqual(sha, sha2)
        sdir = paths.session_dir(sha2)
        self.assertEqual(json.loads(self.r(f"meta/.ingest/{sha2}/claims.json")), {"a": 1})
        self.assertEqual(json.loads(self.r(f"meta/.ingest/{sha2}/plan.json")), {"b": 2})
        self.assertEqual(paths.load_session(sha2)["status"], "open")
        siblings = [d for d in os.listdir(os.path.dirname(sdir)) if d.startswith(sha + "-aborted-")]
        self.assertEqual(len(siblings), 1)
        self.assertTrue(any(n.startswith("staging-aborted-") for n in
                            os.listdir(os.path.join(os.path.dirname(sdir), siblings[0]))))

    def test_begin_archives_closed_session_without_carrying_files(self):
        sha = session.begin(self.raw)
        self.w(f"meta/.ingest/{sha}/claims.json", '{"old": true}')
        sess = paths.load_session(sha)
        sess["status"] = "closed"
        paths.save_session(sha, sess)
        sha2 = session.begin(self.raw)
        self.assertFalse(self.exists(f"meta/.ingest/{sha2}/claims.json"))
        self.assertTrue(any(d.startswith(sha + "-closed-") for d in os.listdir(
            os.path.join(self.root, "meta", ".ingest"))))


class TestThemeInsert(unittest.TestCase):
    def test_inserted_under_papers_before_links(self):
        text = "# T\n\n## Papers\n\n- [[a]]\n\n## Links\n\n- [[z]]\n"
        out = session._insert_under_papers(text, "[[b]]")
        self.assertEqual(out, "# T\n\n## Papers\n\n- [[a]]\n- [[b]]\n\n## Links\n\n- [[z]]\n")

    def test_section_created_before_threads(self):
        out = session._insert_under_papers("# T\n\n## Scope\n\nx\n\n## Threads\n\n- t\n", "[[b]]")
        self.assertLess(out.index("## Papers"), out.index("## Threads"))
        self.assertIn("- [[b]]", out.split("## Threads")[0])

    def test_section_created_at_end(self):
        out = session._insert_under_papers("# T\n\n## Scope\n\nx\n", "[[b]]")
        self.assertTrue(out.endswith("## Papers\n\n- [[b]]\n"))


class TestCommitTarget(unittest.TestCase):
    def test_target_is_plan_slug(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "meta", ".ingest", "abc"))
            with open(os.path.join(root, "meta", ".ingest", "abc", "plan.json"), "w") as f:
                json.dump({"wiki_slug": "paper-2024-x"}, f)
            with patch.object(wrap.core, "ROOT", root):
                t = wrap._target(["wiki/junta.md", "wiki/paper-2024-x.md"], ["finalize", "abc"])
            self.assertEqual(t, "paper-2024-x")
        self.assertEqual(wrap._target(["wiki/a.md", "wiki/b.md"], ["catalog", "x"]), "a")


class TestBookGate(unittest.TestCase):
    def _pdf(self, d, pages, first, toc=None):
        from tests import pdfkit
        doc = pdfkit.Doc()
        for i in range(pages):
            doc.new_page().insert_text((72, 72), first if i == 0 else f"page {i}")
        if toc:
            doc.set_toc(toc)
        path = os.path.join(d, "x.pdf")
        doc.save(path)
        doc.close()
        return path

    def test_long_paper_with_abstract_is_not_a_book(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._pdf(d, 70, "A Paper\nAlice, Bob\nAbstract\nWe show things.")
            self.assertFalse(book.is_book(p))
            rows, blocked = book.gate("raw/x.pdf", p)
            self.assertIsNone(blocked)
            self.assertEqual(rows, [])

    def test_real_book_stays_gated(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._pdf(d, 70, "Analysis of Boolean Functions\nPreface",
                          toc=[[1, "Chapter 1. Intro", 2], [1, "Chapter 2. More", 20], [1, "Chapter 3. End", 40]])
            self.assertTrue(book.is_book(p))

    def test_book_with_abstract_but_chapters_stays_gated(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._pdf(d, 70, "Abstract", toc=[[1, "Chapter 1. Intro", 2]])
            self.assertTrue(book.is_book(p))


class TestCoherenceCli(unittest.TestCase):
    def test_unknown_id_regenerated_before_failing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "w.tsv")
            fresh = {"abc": {"id": "abc", "score": 40, "kind": "internal", "slugs": "a,b",
                             "summary": "s", "status": "open"}}
            with patch.object(coherence, "WARNINGS_PATH", path), \
                    patch.object(coherence, "_regenerate", lambda: fresh):
                self.assertEqual(coherence.cmd_set_status("abc", "dismissed"), 0)
                self.assertEqual(coherence.load_warnings()["abc"]["status"], "dismissed")
                self.assertEqual(coherence.cmd_set_status("nope", "dismissed"), 1)


class TestThemeConcepts(Vault):
    def test_theme_slugs_become_areas_not_concepts(self):
        sha = session.begin(self.raw)
        claims = {"raw": self.raw, "concepts": ["boolean-analysis", "Fourier-Analysis", "junta"]}
        self.w(f"meta/.ingest/{sha}/claims.json", json.dumps(claims))
        with patch.object(map_mod, "validate_claims", lambda c: None), \
                patch.object(map_mod, "wiki_slugs", lambda: {"theme-boolean-analysis", "theme-fourier-analysis"}), \
                patch.object(map_mod, "person_from_raw", lambda r: None):
            plan = map_mod.run_map(sha)
        self.assertEqual([c["slug"] for c in plan["create_concepts"]], ["junta"])
        self.assertIn("boolean-analysis", plan["areas"])
        self.assertIn("fourier-analysis", plan["areas"])
        self.assertEqual({u["moc"] for u in plan["moc_updates"]},
                         {"theme-boolean-analysis", "theme-fourier-analysis"})


if __name__ == "__main__":
    unittest.main()
