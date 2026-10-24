#!/usr/bin/env python3
"""Tests for the backend/src/kb/share scaffold: CLI dispatcher, contracts, KB_ROOT override."""
import datetime
import importlib
import os
import subprocess
import sys
import tempfile
import unittest

from kb.paths import vault_root
ROOT = vault_root()

from kb.share import __main__ as share_main
from kb.share import contracts

PAGE = """---
type: concept
status: seed
related: []
---

# Only page

One-liner.
"""


class DispatcherTests(unittest.TestCase):
    def test_version_subprocess(self):
        proc = subprocess.run([sys.executable, "-m", "kb.share", "version"],
                              capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("share:", proc.stdout)
        self.assertIn("modules:", proc.stdout)
        for name in share_main.load_modules():
            self.assertIn(name.rsplit(".", 1)[-1], proc.stdout)

    def test_no_args_is_usage(self):
        proc = subprocess.run([sys.executable, "-m", "kb.share"],
                              capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 2)

    def test_missing_module_skipped(self):
        loaded = share_main.load_modules(["kb.share.does_not_exist"])
        self.assertEqual(loaded, {})
        self.assertEqual(share_main.main(["version"]), 0)

    def test_broken_module_raises(self):
        # ImportError from *inside* a module must not be swallowed.
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sharetestpkg"))
            open(os.path.join(d, "sharetestpkg", "__init__.py"), "w").close()
            with open(os.path.join(d, "sharetestpkg", "broken.py"), "w") as f:
                f.write("import no_such_module_xyz\n")
            sys.path.insert(0, d)
            try:
                with self.assertRaises(ImportError):
                    share_main.load_modules(["sharetestpkg.broken"])
            finally:
                sys.path.remove(d)
                sys.modules.pop("sharetestpkg", None)


class SnapshotNameTests(unittest.TestCase):
    DATE = datetime.date(2026, 10, 21)

    def test_valid(self):
        self.assertEqual(contracts.snapshot_worker_name("my-snap", self.DATE), "snapshot-20261021-my-snap")
        self.assertEqual(contracts.snapshot_worker_name("v2", self.DATE), "snapshot-20261021-v2")

    def test_invalid(self):
        for bad in ("kb", "KB", "my_snap", "-x", "x-", "", "a" * 70, "snäp", "my snap"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    contracts.snapshot_worker_name(bad, self.DATE)

    def test_length_limit_is_total(self):
        ok = "a" * (63 - len("snapshot-20261021-"))
        self.assertEqual(len(contracts.snapshot_worker_name(ok, self.DATE)), 63)
        with self.assertRaises(ValueError):
            contracts.snapshot_worker_name(ok + "a", self.DATE)


class ManifestTests(unittest.TestCase):
    def test_round_trip_byte_stable(self):
        m = contracts.Manifest(content_ref="kb-0.10.1", content_sha="abc", kb_version="0.10.1",
                               viewer_sha="def", profile="public", sha256="0" * 64,
                               built_at="2026-10-21T10:00:00+00:00")
        text = m.to_json()
        self.assertEqual(contracts.Manifest.from_json(text), m)
        self.assertEqual(contracts.Manifest.from_json(text).to_json(), text)
        keys = [line.split(":")[0].strip().strip('"') for line in text.splitlines()[1:-1]]
        self.assertEqual(keys, sorted(keys))


class StatusFileTests(unittest.TestCase):
    def test_write_read(self):
        with tempfile.TemporaryDirectory() as d:
            sf = contracts.StatusFile(os.path.join(d, "nested", "status.json"))
            self.assertIsNone(sf.read())
            sf.write("deployed", "abc", "0.10.1", "2026-10-21T10:00:00+00:00", url="https://x")
            got = sf.read()
            self.assertEqual(set(got), set(contracts.StatusFile.KEYS))
            self.assertEqual(got["state"], "deployed")
            self.assertEqual(got["url"], "https://x")
            self.assertIsNone(got["error"])
            self.assertEqual([f for f in os.listdir(os.path.join(d, "nested"))], ["status.json"])


class KbRootTests(unittest.TestCase):
    def test_semfind_honours_kb_root(self):
        from kb.search import semfind
        old = os.environ.get("KB_ROOT")
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "wiki"))
            with open(os.path.join(d, "wiki", "only-page.md"), "w", encoding="utf-8") as f:
                f.write(PAGE)
            os.environ["KB_ROOT"] = d
            try:
                importlib.reload(semfind)
                self.assertEqual(semfind.ROOT, d)
                self.assertEqual(list(semfind.load_pages()), ["only-page"])
            finally:
                if old is None:
                    os.environ.pop("KB_ROOT", None)
                else:
                    os.environ["KB_ROOT"] = old
                importlib.reload(semfind)
        self.assertEqual(semfind.ROOT, ROOT)
        self.assertNotIn("only-page", semfind.load_pages())


if __name__ == "__main__":
    unittest.main()
