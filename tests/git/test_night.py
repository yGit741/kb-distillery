#!/usr/bin/env python3
"""Tests for src/kb_distillery/git/night.py — the expiring window in which holds do not block agents."""
import os
import subprocess
import tempfile
import time
import unittest

from kb_distillery.git import night


class NightWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        subprocess.run(["git", "init", "-q", self.root], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_closed_by_default(self):
        self.assertFalse(night.active(self.root))
        self.assertIn("closed", night.describe(self.root))

    def test_start_opens_and_stop_closes(self):
        night.start(self.root, hours=2)
        self.assertTrue(night.active(self.root))
        self.assertIn("open until", night.describe(self.root))
        self.assertTrue(night.stop(self.root))
        self.assertFalse(night.active(self.root))

    def test_window_expires_by_itself(self):
        night.start(self.root, hours=1, now=time.time() - 7200)
        self.assertFalse(night.active(self.root))

    def test_hours_are_capped(self):
        now = time.time()
        end = night.start(self.root, hours=100, now=now)
        self.assertLessEqual(end - now, night.MAX_HOURS * 3600 + 1)

    def test_until_clock_time_is_in_the_future(self):
        now = time.time()
        end = night.start(self.root, until="07:00", now=now)
        self.assertGreater(end, now)
        self.assertLessEqual(end - now, 24 * 3600 + 1)

    def test_garbage_marker_means_closed(self):
        night.start(self.root, hours=1)
        with open(night._path(self.root), "w") as f:
            f.write("not json")
        self.assertFalse(night.active(self.root))


if __name__ == "__main__":
    unittest.main()
