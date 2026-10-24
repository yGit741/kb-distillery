#!/usr/bin/env python3
"""Tests for backend/src/kb/git/proof_nudge.py — the Stop hook that asks frontend/data replies for proof links."""
import json
import os
import tempfile
import unittest

from kb.git import proof_nudge


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


class ProofNudgeTests(unittest.TestCase):
    def decide(self, *calls, reply="done", **extra):
        path = transcript(*calls, reply=reply)
        self.addCleanup(os.unlink, path)
        return proof_nudge.decide({"transcript_path": path, **extra})

    def test_frontend_edit_without_proof_blocks(self):
        out = self.decide(("Edit", {"file_path": "/repo/frontend/src/Graph.tsx"}))
        self.assertEqual(out["decision"], "block")
        self.assertIn("frontend/", out["reason"])

    def test_wiki_write_and_ops_commit_block(self):
        self.assertIsNotNone(self.decide(("Write", {"file_path": "wiki/tensor-rank.md"})))
        self.assertIsNotNone(self.decide(("Bash", {"command": "pixi run ops -- commit 'refine'"})))
        self.assertIsNotNone(self.decide(("Bash", {"command": "pixi run ship -- pr --title x"})))

    def test_proof_line_with_link_passes(self):
        for reply in ("All set.\nProof: http://localhost:5173/graph https://github.com/x/pull/9",
                      "**Proof:** shots/graph-after.png"):
            self.assertIsNone(self.decide(("Edit", {"file_path": "frontend/a.tsx"}), reply=reply), reply)

    def test_proof_line_without_link_still_blocks(self):
        self.assertIsNotNone(self.decide(("Edit", {"file_path": "frontend/a.tsx"}), reply="Proof: trust me"))

    def test_tooling_only_and_read_only_turns_are_silent(self):
        self.assertIsNone(self.decide(("Edit", {"file_path": "backend/src/kb/git/ship.py"})))
        self.assertIsNone(self.decide(("Read", {"file_path": "frontend/a.tsx"}), ("Bash", {"command": "ls wiki"})))

    def test_second_pass_and_missing_transcript_are_silent(self):
        self.assertIsNone(self.decide(("Edit", {"file_path": "frontend/a.tsx"}), stop_hook_active=True))
        self.assertIsNone(proof_nudge.decide({"transcript_path": "/nonexistent"}))

    def test_earlier_turns_do_not_count(self):
        path = transcript(("Edit", {"file_path": "frontend/a.tsx"}))
        with open(path, "a") as f:
            f.write("\n" + json.dumps({"type": "user", "message": {"content": "thanks, what is a tensor?"}}))
            f.write("\n" + json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "…"}]}}))
        self.addCleanup(os.unlink, path)
        self.assertIsNone(proof_nudge.decide({"transcript_path": path}))


if __name__ == "__main__":
    unittest.main()
