"""The engine checkout is not a knowledge base: knowledge state must never be written into it."""
import os
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.config import kb as kbconfig


class EngineCheckoutGuardTests(unittest.TestCase):
    def test_engine_checkout_without_kb_toml_is_refused(self):
        root = kbconfig.checkout_root()
        self.assertIsNotNone(root)
        self.assertTrue(kbconfig.is_engine_checkout(root))
        with self.assertRaises(kbconfig.KbConfigError) as cm:
            kbconfig.require_kb_root(root, "knowledge ops")
        self.assertIn("--kb", str(cm.exception))

    def test_folder_with_kb_toml_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, kbconfig.CONFIG_NAME), "w", encoding="utf-8") as f:
                f.write("")
            with patch.object(kbconfig, "checkout_root", return_value=tmp), patch.object(kbconfig, "primary_root", return_value=tmp):
                self.assertFalse(kbconfig.is_engine_checkout(tmp))
                kbconfig.require_kb_root(tmp)

    def test_other_folders_are_not_the_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(kbconfig.is_engine_checkout(tmp))

    def test_ops_dir_and_nightly_sync_refuse_the_engine_root(self):
        from kb_distillery.ops import core, daily_sync
        root = kbconfig.checkout_root()
        with self.assertRaises(kbconfig.KbConfigError):
            core._ops_dir(root)
        with patch.object(daily_sync, "ROOT", root):
            self.assertEqual(daily_sync.main(["--dry-run"]), 2)


if __name__ == "__main__":
    unittest.main()
