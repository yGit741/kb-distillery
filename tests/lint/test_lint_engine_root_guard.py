#!/usr/bin/env python3
"""lint refuses to run (and writes nothing) when no knowledge base is selected: ROOT would be the engine checkout."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

from kb_distillery import paths
from kb_distillery.lint import lint


class EngineRootGuard(unittest.TestCase):
    def test_refuses_when_root_is_the_engine_checkout(self):
        engine = tempfile.mkdtemp(prefix="kb-engine-")
        err = io.StringIO()
        with mock.patch.object(lint, "ROOT", engine), mock.patch.object(paths, "CHECKOUT_ROOT", engine), \
                mock.patch.object(sys, "argv", ["lint"]), contextlib.redirect_stderr(err), \
                mock.patch.object(lint, "collect_snapshot", side_effect=AssertionError("must not run")):
            self.assertEqual(lint.main(), 2)
        self.assertIn("no knowledge base selected", err.getvalue())
        self.assertEqual(os.listdir(engine), [])

    def test_coherence_only_is_refused_too(self):
        engine = tempfile.mkdtemp(prefix="kb-engine-")
        with mock.patch.object(lint, "ROOT", engine), mock.patch.object(paths, "CHECKOUT_ROOT", engine), \
                mock.patch.object(sys, "argv", ["lint", "--coherence-only"]), \
                contextlib.redirect_stderr(io.StringIO()), \
                mock.patch.object(lint, "_coherence_only_main", side_effect=AssertionError("must not run")):
            self.assertEqual(lint.main(), 2)
        self.assertEqual(os.listdir(engine), [])

    def test_a_checkout_that_is_itself_a_vault_gets_past_the_guard(self):
        root = tempfile.mkdtemp(prefix="kb-legacy-")
        os.makedirs(os.path.join(root, "wiki"))
        with mock.patch.object(lint, "ROOT", root), mock.patch.object(paths, "CHECKOUT_ROOT", root), \
                mock.patch.object(sys, "argv", ["lint"]), \
                mock.patch.object(lint, "collect_snapshot", side_effect=RuntimeError("reached")):
            with self.assertRaisesRegex(RuntimeError, "reached"):
                lint.main()

    def test_a_selected_knowledge_base_gets_past_the_guard(self):
        engine, kb = tempfile.mkdtemp(prefix="kb-engine-"), tempfile.mkdtemp(prefix="kb-sel-")
        with mock.patch.object(lint, "ROOT", kb), mock.patch.object(paths, "CHECKOUT_ROOT", engine), \
                mock.patch.object(sys, "argv", ["lint"]), \
                mock.patch.object(lint, "collect_snapshot", side_effect=RuntimeError("reached")):
            with self.assertRaisesRegex(RuntimeError, "reached"):
                lint.main()


if __name__ == "__main__":
    unittest.main()
