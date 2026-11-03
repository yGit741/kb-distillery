"""examples/launchd/switch.sh --dry-run: prints the plan and changes nothing; --rollback --dry-run reads a backup."""
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "examples/launchd/switch.sh"
OLD = ["com.thesis-kb.daily-sync", "com.thesis-kb.deploy-owner"]


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
            for p in sorted(root.rglob("*"))}


@unittest.skipUnless(SCRIPT.is_file(), "owner migration script: export-ignored from the public repo")
class SwitchSh(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(os.path.realpath(tmp.name))
        self.agents = self.home / "Library/LaunchAgents"
        self.agents.mkdir(parents=True)

    def run_switch(self, *args):
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=60)

    def test_dry_run_prints_plan_and_changes_nothing(self):
        for label in OLD:
            (self.agents / f"{label}.plist").write_text(f"<plist>{label}</plist>")
        before = snapshot(self.home)
        r = self.run_switch("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("DRY RUN", out)
        self.assertIn(".kb-distillery-backup/", out)
        for label in OLD:
            self.assertIn(f"cp -p {self.agents}/{label}.plist", out)
            self.assertIn(f"launchctl bootout gui/{os.getuid()}/{label}", out)
            self.assertIn(f"rm -f {self.agents}/{label}.plist", out)
        self.assertIn("install.sh", out)
        self.assertIn("install-deploy-owner.sh", out)
        self.assertIn("com.kb-distillery.daily-sync", out)
        self.assertIn("com.kb-distillery.deploy-owner", out)
        for banned in ("wrangler", "deploy-main", "share --", "cloudflare"):
            self.assertNotIn(banned, out.lower().replace("install-deploy-owner", ""))
        self.assertEqual(snapshot(self.home), before)

    def test_dry_run_with_nothing_old_is_a_noop_plan(self):
        before = snapshot(self.home)
        r = self.run_switch("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing to back up", r.stdout)
        self.assertIn("already switched", r.stdout)
        self.assertEqual(snapshot(self.home), before)

    def test_rollback_dry_run_with_fake_backup(self):
        bdir = self.agents / ".kb-distillery-backup/20261101-120000"
        bdir.mkdir(parents=True)
        for label in OLD:
            (bdir / f"{label}.plist").write_text("<plist/>")
        (bdir / "loaded.txt").write_text(OLD[0] + "\n")
        (self.agents / "com.kb-distillery.daily-sync.plist").write_text("<plist/>")
        before = snapshot(self.home)
        r = self.run_switch("--rollback", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn(f"restoring from {bdir}", out)
        self.assertIn(f"rm -f {self.agents}/com.kb-distillery.daily-sync.plist", out)
        self.assertIn(f"cp -p {bdir}/{OLD[0]}.plist {self.agents}/{OLD[0]}.plist", out)
        self.assertIn(f"launchctl bootstrap gui/{os.getuid()} {self.agents}/{OLD[0]}.plist", out)
        self.assertIn(f"left unloaded (was not loaded before): {OLD[1]}", out)
        self.assertEqual(snapshot(self.home), before)

    def test_rollback_without_backup_fails_cleanly(self):
        r = self.run_switch("--rollback", "--dry-run")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no backup", r.stderr)

    def test_unknown_flag_is_refused(self):
        self.assertEqual(self.run_switch("--bogus").returncode, 2)


if __name__ == "__main__":
    unittest.main()
