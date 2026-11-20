"""The Review deck (proposals/review.py): one card per hunk, its blast radius, batch apply, rewrite of one card from
one sentence, split where the model says. On a temp kb repo; the model is mocked (no LLM call)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from kb_distillery.proposals import review, service

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "KB_NO_PUSH": "1", "KB_SHARE_AUTODEPLOY": "0"}

PAGE = ("---\ntype: concept\ntitle: {n}\ndescription: About {n}.\n---\n\n# {n}\n\n"
        "The first claim is strong.\n\nA second paragraph links [Beta](beta.md).\n\n## Details\n\nMore text here.\n")


def vcs(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout.strip()


def make_kb(root: Path, pages=("alpha", "beta")) -> Path:
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "index.md").write_text("v1\n", encoding="utf-8")
    (root / "wiki" / "log.md").write_text("# Log\n", encoding="utf-8")
    (root / ".gitignore").write_text("meta/.ops/\n.local/\n", encoding="utf-8")
    for slug in pages:
        (root / "wiki" / f"{slug}.md").write_text(PAGE.format(n=slug), encoding="utf-8")
    vcs(root, "init", "-q", "-b", "main")
    vcs(root, "config", "user.name", "t")
    vcs(root, "config", "user.email", "t@example.com")
    vcs(root, "add", "-A")
    vcs(root, "commit", "-q", "-m", "chore: init (retro)")
    return root


def reply(text):
    return SimpleNamespace(ok=True, text=text, error="")


class DeckTest(unittest.TestCase):
    def setUp(self):
        self.review, self.service = review, service
        self.tmp = tempfile.TemporaryDirectory()
        self.root = str(make_kb(Path(self.tmp.name) / "kb"))
        patches = [mock.patch.dict(os.environ, ENV), mock.patch.object(service, "DEFAULT_ROOT", self.root),
                   mock.patch("kb_distillery.ops.core.run_lint", return_value=None),
                   mock.patch("kb_distillery.ops.core.okf_gate", return_value=None),
                   mock.patch("kb_distillery.publish.cloudflare.autodeploy.trigger", return_value="skipped")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, slug):
        return Path(self.root, "wiki", f"{slug}.md").read_text(encoding="utf-8")

    def propose(self, slug="alpha"):
        text = self.page(slug).replace("The first claim is strong.", "The first claim is weaker.")
        text = text.replace("More text here.", "More careful text here.")
        return self.service.create("Two edits", [{"kind": "edit_page", "slug": slug, "new_text": text}], root=self.root)

    def test_one_card_per_hunk_with_context(self):
        p = self.propose()
        deck = self.review.deck(self.root)
        self.assertEqual(len(deck["cards"]), 2)
        self.assertEqual({c["proposal_id"] for c in deck["cards"]}, {p["id"]})
        first = next(c for c in deck["cards"] if "weaker" in c["hunk"]["after"])
        self.assertEqual(first["page_title"], "alpha")
        self.assertIn("# alpha", first["context_before"])
        self.assertIn("second paragraph", first["context_after"])
        self.assertEqual(deck["proposals"][0]["hunks"], 2)

    def test_each_card_carries_its_blast_radius(self):
        self.propose("alpha")
        self.propose("beta")
        reach = {c["hunk"]["slug"]: c["reach"] for c in self.review.deck(self.root)["cards"]}
        self.assertEqual(reach["alpha"], {"total": 1, "pages": [{"slug": "beta", "title": "beta", "type": "concept", "rel": "out", "exists": True}]})
        self.assertEqual(reach["beta"]["pages"], [{"slug": "alpha", "title": "alpha", "type": "concept", "rel": "in", "exists": True}])

    def test_rewrite_sends_the_marked_passages_and_picked_pages(self):
        p = self.propose()
        weak = next(h for h in p["hunks"] if "weaker" in h["after"])
        answer = '{"reply": "Linked it.", "after": "The first claim is weaker, see [beta](beta.md)."}'
        with mock.patch.object(self.review.llm, "ask", return_value=reply(answer)) as ask:
            self.review.rewrite(p["id"], weak["id"], "link the related page", root=self.root,
                                marks=["  claim is   weaker ", "claim is weaker"], pages=["beta", "nope"])
        prompt = ask.call_args[0][0]
        self.assertEqual(prompt.count('- "claim is weaker"'), 1)
        self.assertIn("## beta (`beta`)", prompt)
        self.assertIn("A second paragraph links", prompt)
        self.assertNotIn("nope", prompt)

    def test_batch_applies_rejects_or_waits(self):
        a, b = self.propose("alpha"), self.propose("beta")
        ha = [h["id"] for h in a["hunks"]]
        hb = [h["id"] for h in b["hunks"]]
        out = self.review.apply_batch([
            {"proposal_id": a["id"], "decisions": [{"hunk_id": ha[0], "decision": "accept"},
                                                   {"hunk_id": ha[1], "decision": "reject"}]},
            {"proposal_id": b["id"], "decisions": [{"hunk_id": hb[0], "decision": "reject"}]},
        ], root=self.root)
        self.assertEqual([x["id"] for x in out["applied"]], [a["id"]])
        self.assertEqual(out["applied"][0]["pages"], ["alpha"])
        self.assertTrue(out["applied"][0]["commit"])
        self.assertEqual(out["waiting"], [{"id": b["id"], "title": "Two edits", "undecided": 1}])
        self.assertIn("weaker", self.page("alpha"))
        self.assertIn("More text here.", self.page("alpha"))
        out = self.review.apply_batch([{"proposal_id": b["id"], "decisions": [{"hunk_id": hb[1], "decision": "reject"}]}],
                                      root=self.root)
        self.assertEqual(out["rejected"], [b["id"]])
        self.assertEqual(self.service.get(b["id"], root=self.root)["status"], "rejected")

    def test_rewrite_changes_only_that_card(self):
        p = self.propose()
        weak = next(h for h in p["hunks"] if "weaker" in h["after"])
        other = next(h for h in p["hunks"] if h["id"] != weak["id"])
        self.service.decide(p["id"], [{"hunk_id": other["id"], "decision": "accept"}], root=self.root)
        answer = '{"reply": "Softened it.", "after": "The first claim is plausible."}'
        with mock.patch.object(self.review.llm, "ask", return_value=reply(answer)) as ask:
            out = self.review.rewrite(p["id"], weak["id"], "make it softer", root=self.root)
        self.assertIn("make it softer", ask.call_args[0][0])
        self.assertEqual(out["reply"], "Softened it.")
        self.assertEqual(out["others_changed"], [])
        new = next(h for h in out["proposal"]["hunks"] if h["id"] == out["hunk_id"])
        self.assertIn("plausible", new["after"])
        self.assertEqual(out["proposal"]["decisions"][other["id"]]["decision"], "accept")
        self.assertEqual(out["proposal"]["revision"], 2)
        back = self.review.revert(p["id"], root=self.root)
        self.assertEqual(back["revision"], 3)
        self.assertIn(weak["id"], [h["id"] for h in back["hunks"]])

    def test_rewrite_refuses_a_link_rewrite_and_an_empty_sentence(self):
        from kb_distillery.proposals.model import ProposalError
        p = self.service.create("Relink", [{"kind": "rewrite_link", "slug": "alpha", "from_slug": "beta",
                                            "to_slug": "gamma"}], root=self.root)
        with self.assertRaises(ProposalError) as e:
            self.review.rewrite(p["id"], p["hunks"][0]["id"], "do it", root=self.root)
        self.assertEqual(e.exception.status, 400)
        with self.assertRaises(ProposalError):
            self.review.rewrite(p["id"], p["hunks"][0]["id"], "  ", root=self.root)

    def test_split_where_the_model_says(self):
        info = self.review.restructure.blocks("alpha", root=self.root)
        cut = next(b["index"] for b in info["blocks"] if b["text"].startswith("## Details"))
        answer = f'{{"reply": "Details stand alone.", "cuts": [{cut}, 999], "titles": ["Alpha details", "bogus"]}}'
        with mock.patch.object(self.review.llm, "ask", return_value=reply(answer)):
            out = self.review.split("alpha", root=self.root)
        self.assertEqual(out["cuts"], [cut])
        self.assertEqual(out["titles"], ["Alpha details"])
        self.assertEqual(out["proposal"]["producer"]["kind"], "restructure")

    def test_rewrite_of_the_second_card_lands_on_the_second_edit(self):
        p = self.propose()
        later = next(h for h in p["hunks"] if "careful" in h["after"])
        answer = '{"reply": "Done.", "after": "Much more careful text here."}'
        with mock.patch.object(self.review.llm, "ask", return_value=reply(answer)):
            out = self.review.rewrite(p["id"], later["id"], "stronger wording", root=self.root)
        afters = [h["after"] for h in out["proposal"]["hunks"]]
        self.assertTrue(any("Much more careful text here." in a for a in afters))
        self.assertTrue(any("The first claim is weaker." in a for a in afters))   # the first card is untouched
        self.assertFalse(any("weaker" in a and "Much more" in a for a in afters))

    def test_a_proposal_changed_during_the_model_call_is_not_overwritten(self):
        from kb_distillery.proposals.model import ProposalError
        p = self.propose()
        weak = next(h for h in p["hunks"] if "weaker" in h["after"])

        def meanwhile(*_a, **_k):
            self.service.reject(p["id"], root=self.root)
            return reply('{"reply": "Softened it.", "after": "The first claim is plausible."}')

        with mock.patch.object(self.review.llm, "ask", side_effect=meanwhile), self.assertRaises(ProposalError) as e:
            self.review.rewrite(p["id"], weak["id"], "make it softer", root=self.root)
        self.assertEqual(e.exception.status, 409)
        self.assertEqual(self.service.get(p["id"], root=self.root)["status"], "rejected")


