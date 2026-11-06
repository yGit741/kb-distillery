"""ship sync / merge auto-resolve a merge whose only conflicts are in the feature-flag files."""
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kb_distillery.config.flags import codegen
from kb_distillery.git import flag_merge, ship
from tests.git.test_ship import FAKE_GH, _g
from tests.needs_git import needs_git

PREAMBLE = "# registry\n\n"


def _flag(name):
    return (f'[[flag]]\nname = "{name}"\ndescription = "d {name}"\nowner = "me"\ncreated = 2026-11-01\n'
            f'expires = 2027-11-01\nkind = "runtime"\ndefault = false\nenvs = {{ local = true, private = false, public = false }}\n')


def _toml(*names):
    return PREAMBLE + "\n".join(_flag(n) for n in names)


class MergeFlagsTomlTests(unittest.TestCase):
    def test_union_keeps_order_and_dedupes(self):
        base = _toml("a")
        out = flag_merge.merge_flags_toml(_toml("a", "b", "c"), _toml("a", "c", "d"), base)
        names = re.findall(r'^name = "(.*)"', out, re.M)
        self.assertEqual(names, ["a", "b", "c", "d"])

    def test_one_sided_edit_is_kept_from_either_side(self):
        base = _toml("a", "b")
        flipped = base.replace("local = true", "local = false", 1)      # a: changed on one side only
        names = lambda t: re.findall(r'^name = "(.*)"', t, re.M)
        out = flag_merge.merge_flags_toml(_toml("a", "b", "mine"), flipped, base)      # theirs edited a
        self.assertEqual(names(out), ["a", "b", "mine"])
        self.assertIn("local = false", out.split("[[flag]]")[1])
        out = flag_merge.merge_flags_toml(flipped, _toml("a", "b", "new"), base)       # ours edited a
        self.assertEqual(names(out), ["a", "b", "new"])
        self.assertIn("local = false", out.split("[[flag]]")[1])

    def test_delete_vs_change(self):
        base = _toml("a", "b")
        self.assertEqual(re.findall(r'^name = "(.*)"', flag_merge.merge_flags_toml(_toml("b"), base, base), re.M), ["b"])
        self.assertIsNone(flag_merge.merge_flags_toml(_toml("b"), base.replace("d a", "x"), base))

    def test_header_comments_travel_with_their_block(self):
        base = _toml("a")
        theirs = base + "\n# about new\n" + _flag("new")
        out = flag_merge.merge_flags_toml(_toml("a", "mine"), theirs, base)
        self.assertIn("# about new\n[[flag]]\nname = \"new\"", out)
        self.assertNotIn("# about new\n[[flag]]\nname = \"mine\"", out)
        ours = base + "\n# about mine\n" + _flag("mine")
        out = flag_merge.merge_flags_toml(ours, _toml("a", "new"), base)
        self.assertIn("# about mine\n[[flag]]\nname = \"mine\"", out)
        self.assertIsNone(flag_merge.merge_flags_toml("# one\n\n" + _toml("a"), "# two\n\n" + _toml("a"), _toml("a")))

    def test_edit_on_both_sides_is_not_resolved(self):
        base = _toml("a")
        self.assertIsNone(flag_merge.merge_flags_toml(_toml("a").replace("d a", "mine"), _toml("a").replace("d a", "theirs"), base))


@needs_git
class FlagSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        remote, self.repo = os.path.join(t, "remote.git"), os.path.join(t, "repo")
        _g(t, "init", "-q", "--bare", "-b", "main", remote)
        _g(t, "clone", "-q", remote, self.repo)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            _g(self.repo, "config", k, v)
        gh_dir = os.path.join(t, "gh")
        os.makedirs(gh_dir)
        gh = os.path.join(gh_dir, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.env = patch.dict(os.environ, {"GH_BIN": gh, "FAKE_GH_DIR": gh_dir,
                                           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        self.env.start()
        self._write(self.repo, ".gitignore", ".claude/worktrees/\n")
        for s in ("home", "graph", "pages"):
            self._write(self.repo, f"web/src/features/{s}/index.tsx", "")
        self._flags(self.repo, "a")
        self._write(self.repo, "meta/tool.py", "x\n")
        self._write(self.repo, flag_merge.FLAGS_TEST,
                    "    self.assertIn('export type FlagName = \"old\";', gen)\n")
        self._regen(self.repo)
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m", "chore: init (retro)")
        _g(self.repo, "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    @staticmethod
    def _write(root, rel, text):
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)

    def _flags(self, root, *names):
        self._write(root, flag_merge.FLAGS_TOML, _toml(*names))

    def _regen(self, root):
        self.assertEqual(codegen.main(["--flags", os.path.join(root, flag_merge.FLAGS_TOML)], root=root), 0)
        union = re.search(r"export type FlagName = [^;]*;", (Path(root) / codegen.GEN_TS).read_text()).group(0)
        pin = Path(root) / flag_merge.FLAGS_TEST
        pin.write_text(re.sub(r"export type FlagName = [^;]*;", lambda _m: union, pin.read_text()))

    def _land(self, root, *names, extra=None, msg="feat(flags): add"):
        """Add flag(s) (and regenerated files, like a real PR) in `root`, commit."""
        self._flags(root, "a", *names)
        self._regen(root)
        for rel, text in (extra or {}).items():
            self._write(root, rel, text)
        _g(root, "add", "-A")
        _g(root, "commit", "-q", "-m", msg)

    def _main_adds(self, *names, extra=None):
        self._land(self.repo, *names, extra=extra, msg="feat(flags): theirs (#9)")
        _g(self.repo, "push", "-q", "origin", "main")

    def _branch(self, feature="flagsync"):
        self.assertEqual(ship.cmd_start(feature, worktree=True, root=self.repo), 0)
        return os.path.join(self.repo, ".claude", "worktrees", feature)

    def test_flags_only_conflict_is_resolved_and_committed(self):
        wt = self._branch()
        self._land(wt, "mine")
        self._main_adds("theirs")
        self.assertEqual(ship.cmd_sync(root=wt, gates=False), 0)
        self.assertEqual(len(_g(wt, "rev-list", "--parents", "-n1", "HEAD").split()), 3)   # a merge commit
        text = Path(wt, flag_merge.FLAGS_TOML).read_text()
        self.assertEqual(re.findall(r'^name = "(.*)"', text, re.M), ["a", "mine", "theirs"])
        gen = Path(wt, codegen.GEN_TS).read_text()
        self.assertIn('"a" | "mine" | "theirs"', gen)
        self.assertIn('FlagName = "a" | "mine" | "theirs";', Path(wt, flag_merge.FLAGS_TEST).read_text())
        self.assertEqual(_g(wt, "status", "--short"), "")
        self.assertEqual(codegen.main(["--check", "--flags", os.path.join(wt, flag_merge.FLAGS_TOML)], root=wt), 0)

    def test_main_edit_of_an_existing_flag_survives_the_sync(self):
        wt = self._branch("edit")
        self._land(wt, "mine")
        self._write(self.repo, flag_merge.FLAGS_TOML,
                    _toml("a").replace("local = true", "local = false"))
        self._regen(self.repo)
        _g(self.repo, "add", "-A")
        _g(self.repo, "commit", "-q", "-m", "feat(flags): release a (#9)")
        _g(self.repo, "push", "-q", "origin", "main")
        self.assertEqual(ship.cmd_sync(root=wt, gates=False), 0)
        text = Path(wt, flag_merge.FLAGS_TOML).read_text()
        self.assertEqual(re.findall(r'^name = "(.*)"', text, re.M), ["a", "mine"])
        self.assertIn("local = false", text.split("[[flag]]")[1])

    def test_same_flag_name_on_both_sides_is_kept_once(self):
        wt = self._branch("dup")
        self._land(wt, "same")
        self._main_adds("same", "theirs")
        self.assertEqual(ship.cmd_sync(root=wt, gates=False), 0)
        text = Path(wt, flag_merge.FLAGS_TOML).read_text()
        self.assertEqual(re.findall(r'^name = "(.*)"', text, re.M), ["a", "same", "theirs"])

    def test_conflict_in_another_file_still_stops(self):
        wt = self._branch("other")
        self._land(wt, "mine", extra={"meta/tool.py": "mine\n"})
        self._main_adds("theirs", extra={"meta/tool.py": "theirs\n"})
        self.assertEqual(ship.cmd_sync(root=wt, gates=False), 1)
        self.assertIn("meta/tool.py", _g(wt, "diff", "--name-only", "--diff-filter=U"))
        self.assertEqual(ship.cmd_sync(cont=True, root=wt, gates=False), 1)    # still unresolved
        self.assertIn("<<<<<<<", Path(wt, flag_merge.FLAGS_TOML).read_text())  # flag files left alone too
        self.assertEqual(ship.cmd_sync(abort=True, root=wt, gates=False), 0)
