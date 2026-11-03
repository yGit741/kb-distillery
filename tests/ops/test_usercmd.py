"""ops.usercmd: the commands the System screen shows match how kb-distillery was installed."""
import unittest

from kb_distillery.ops.usercmd import localize, user_command


class UserCommand(unittest.TestCase):
    def test_a_checkout_keeps_pixi_commands(self):
        self.assertEqual(user_command("pixi run ops -- commit", True), "pixi run ops -- commit")

    def test_a_wheel_install_gets_distill(self):
        self.assertEqual(user_command('pixi run ops -- record refine <target> "summary"   # or wait', False),
                         'distill ops record refine <target> "summary"   # or wait')
        self.assertEqual(user_command("pixi run share -- prune --apply", False), "distill share prune --apply")

    def test_repository_tooling_has_no_distill_form(self):
        for cmd in ("pixi run install-sync", "pixi run ship -- prune --apply", "cd x && pixi run lanes", "pixi run daily-sync"):
            self.assertEqual(user_command(cmd, False), "", cmd)

    def test_other_text_and_empty_pass_through(self):
        self.assertEqual(user_command("git worktree prune", False), "git worktree prune")
        self.assertEqual(user_command("", False), "")

    def test_localize_rewrites_fix_and_next_anywhere_in_a_snapshot(self):
        snap = {"threads": [{"next": "pixi run ops -- commit", "title": "pixi run ops -- x"}],
                "hygiene": {"findings": [{"fix": "pixi run install-sync"}]}, "n": 1}
        localize(snap, False)
        self.assertEqual(snap["threads"][0], {"next": "distill ops commit", "title": "pixi run ops -- x"})
        self.assertEqual(snap["hygiene"]["findings"][0]["fix"], "")


if __name__ == "__main__":
    unittest.main()
