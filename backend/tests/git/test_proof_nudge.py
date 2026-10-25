#!/usr/bin/env python3
"""Tests for backend/src/kb/git/proof_nudge.py — the Stop hook that asks each kind of work for its proof links."""
import json
import os
import tempfile
import unittest

from kb.git import proof_nudge

LOCAL = "http://localhost:5173/graph"
SITE = "https://kb.yonatan-magen-thesis.workers.dev/graph"
PR = "https://github.com/yGit741/yonatan-thesis-kb/pull/9"


def transcript(*tool_calls, reply="done", human="please change the graph"):
    """A minimal transcript: a human message, assistant tool calls (each with a result), then the reply."""
    lines = [{"type": "user", "message": {"content": human}}]
    for name, inp in tool_calls:
        lines.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})
        lines.append({"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}})
    lines.append({"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}})
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    f.write("\n".join(json.dumps(l) for l in lines))
    f.close()
    return f.name


UI = ("Edit", {"file_path": "/repo/frontend/src/Graph.tsx"})


class ProofNudgeTests(unittest.TestCase):
    def decide(self, *calls, reply="done", **extra):
        path = transcript(*calls, reply=reply)
        self.addCleanup(os.unlink, path)
        return proof_nudge.decide({"transcript_path": path, **extra})

    def test_ui_needs_local_and_deployed(self):
        out = self.decide(UI, reply=f"Proof: {LOCAL}")
        self.assertEqual(out["decision"], "block")
        self.assertIn("deployed URL", out["reason"])
        self.assertNotIn("local URL", out["reason"])
        self.assertIsNone(self.decide(UI, reply=f"Proof: {LOCAL} {SITE}"))

    def test_ui_screenshot_stands_in_for_deployed_not_local(self):
        self.assertIsNone(self.decide(UI, reply=f"**Proof:** {LOCAL} shots/graph-after.png"))
        self.assertIsNotNone(self.decide(UI, reply="Proof: shots/graph-after.png"))

    def test_knowledge_needs_page_and_version(self):
        w = ("Write", {"file_path": "wiki/tensor-rank.md"})
        self.assertIn("kb-x.y.z", self.decide(w, reply=f"Proof: {SITE}/tensor-rank")["reason"])
        self.assertIsNone(self.decide(w, reply=f"Proof: {SITE}/tensor-rank (kb-1.2.3)"))

    def test_pr_and_deploy_kinds(self):
        ship = ("Bash", {"command": "pixi run ship -- merge"})
        self.assertIsNotNone(self.decide(ship, reply="Proof: merged"))
        self.assertIsNone(self.decide(ship, reply=f"Proof: {PR}"))
        share = ("Bash", {"command": "pixi run share -- deploy"})
        self.assertIsNone(self.decide(share, reply=f"Proof: {SITE}"))

    def test_kinds_accumulate(self):
        out = self.decide(UI, ("Bash", {"command": "pixi run ship -- pr"}), reply=f"Proof: {LOCAL} {SITE}")
        self.assertIn("pr:", out["reason"])
        self.assertIsNone(self.decide(UI, ("Bash", {"command": "pixi run ship -- pr"}),
                                      reply=f"Proof: {LOCAL} {SITE}\nProof: {PR}"))

    def test_api_needs_local_endpoint(self):
        api = ("Edit", {"file_path": "backend/src/kb/api/routes.py"})
        self.assertIsNotNone(self.decide(api, reply=f"Proof: {PR}"))
        self.assertIsNone(self.decide(api, reply="Proof: http://127.0.0.1:8000/api/notes"))

    def test_tooling_only_and_read_only_turns_are_silent(self):
        self.assertIsNone(self.decide(("Edit", {"file_path": "backend/src/kb/git/ship.py"})))
        self.assertIsNone(self.decide(("Read", {"file_path": "frontend/a.tsx"}), ("Bash", {"command": "ls wiki"})))

    def test_second_pass_and_missing_transcript_are_silent(self):
        self.assertIsNone(self.decide(UI, stop_hook_active=True))
        self.assertIsNone(proof_nudge.decide({"transcript_path": "/nonexistent"}))

    def test_earlier_turns_do_not_count(self):
        path = transcript(UI)
        with open(path, "a") as f:
            f.write("\n" + json.dumps({"type": "user", "message": {"content": "thanks, what is a tensor?"}}))
            f.write("\n" + json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "…"}]}}))
        self.addCleanup(os.unlink, path)
        self.assertIsNone(proof_nudge.decide({"transcript_path": path}))


if __name__ == "__main__":
    unittest.main()
