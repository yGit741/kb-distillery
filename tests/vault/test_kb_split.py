"""The explorer / knowledge-base split: the base kit's defaults fallback, digest instructions, the shared think guard, the
think-repo commit policy, lanes for kb.toml / digest/ / the kit defaults, and /api/kb's facts."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

from kb_distillery import kbconfig, paths
from kb_distillery.config import resources
from kb_distillery.vault import digest, schema
from kb_distillery.git import commit_policy as cp
from kb_distillery.git import guard


class MetaDefaults(unittest.TestCase):
    def test_the_defaults_are_the_base_kits_package_data(self):
        self.assertEqual(paths.META_DEFAULTS_PATH, str(resources.resource("kits/base/defaults")))
        self.assertTrue(os.path.isfile(os.path.join(paths.META_DEFAULTS_PATH, "flags.toml")))
        own = paths.vpath("digest")           # the kb's own digest/ wins; without one the base kit's defaults/digest answers
        self.assertEqual(paths.DIGEST_INSTRUCTIONS_PATH, own if os.path.isdir(own) else os.path.join(paths.META_DEFAULTS_PATH, "digest"))
        self.assertTrue(os.path.isfile(os.path.join(paths.META_DEFAULTS_PATH, "digest", "focus.md")))

    def test_kb_meta_overrides_the_explorer_default(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(paths.meta_file("flags.toml", root=d), os.path.join(paths.META_DEFAULTS_PATH, "flags.toml"))
            os.makedirs(os.path.join(d, "meta"))
            with open(os.path.join(d, "meta", "flags.toml"), "w") as f:
                f.write("")
            self.assertEqual(paths.meta_file("flags.toml", root=d), os.path.join(d, "meta", "flags.toml"))
            # nothing anywhere: the kb path, so a write lands in the kb
            self.assertEqual(paths.meta_file("nope.md", root=d), os.path.join(d, "meta", "nope.md"))

    def test_digest_instructions_fall_back_to_the_explorer(self):
        with tempfile.TemporaryDirectory() as d:
            parts = digest.instruction_files(root=d)
            self.assertEqual({p: o for p, (_path, o) in parts.items()}, {"focus.md": "explorer", "types.md": "explorer"})
            os.makedirs(os.path.join(d, "digest"))
            with open(os.path.join(d, "digest", "focus.md"), "w") as f:
                f.write("# mine\n")
            parts = digest.instruction_files(root=d)
            self.assertEqual(parts["focus.md"][1], "kb")
            self.assertEqual(parts["types.md"][1], "explorer")
            self.assertTrue(digest.digest_instructions(root=d).startswith("# mine"))


class SharedThink(unittest.TestCase):
    def test_guard_blocks_the_shared_think_space_by_absolute_path(self):
        with self.assertRaises(SystemExit) as cm, redirect_stderr(io.StringIO()):
            guard._shared_think_guard(os.path.join(paths.THINK_PATH, "note.md"))
        self.assertEqual(cm.exception.code, 2)
        guard._shared_think_guard(os.path.join(paths.ROOT, "wiki", "x.md"))      # elsewhere: silent

    def test_kb_think_commits_pass_in_the_think_repo_and_only_there(self):
        msg = ("kb(think): human edits (1 file) (kb-1.3.9)\n\nKB-Version: 1.3.9\nKB-Op: think\nKB-Target: think\n"
               "KB-Actor: human\n")
        self.assertEqual(cp.check_message(msg, "main", ["Points to meeting.md"], think_repo=True), [])
        self.assertTrue(cp.check_message(msg, "main", ["Points to meeting.md"]))   # a bare path in a kb repo: refused

    def test_lint_wants_the_think_citation(self):
        from kb_distillery.distill.paths import resolve_think_path, think_cite
        self.assertEqual(think_cite(resolve_think_path("note")), "think:note.md")
        self.assertEqual(resolve_think_path("think:note.md"), "think/note.md")


class Lanes(unittest.TestCase):
    def test_kb_config_and_digest_are_knowledge_and_the_kit_defaults_are_tooling(self):
        self.assertEqual(schema.lane_of("kb.toml"), "knowledge")
        self.assertEqual(schema.lane_of("digest/focus.md"), "knowledge")
        self.assertEqual(schema.lane_of("src/kb_distillery/kits/base/defaults/flags.toml"), "tooling")
        self.assertIn("digest", schema.ROOT_DIRS)
        self.assertIn("kb.toml", schema.ROOT_FILES)

    def test_guard_allows_markdown_under_digest_and_the_kit_defaults(self):
        for rel in ("digest/focus.md", "src/kb_distillery/kits/base/defaults/docs/dev.md",
                    "src/kb_distillery/kits/base/defaults/digest/types.md"):
            with tempfile.TemporaryDirectory() as d:
                guard.check_path(rel, d)      # no SystemExit


class KbService(unittest.TestCase):
    def test_active_reports_the_selected_kb(self):
        from kb_distillery.services import kb as svc
        info = svc.active()
        self.assertEqual(info["root"], paths.ROOT)
        self.assertEqual({t["id"] for t in info["types"]}, set(schema.TYPE_ORDER))
        self.assertEqual(info["think_root"], paths.THINK_PATH)
        self.assertIn(info["flags_registry"], ("explorer", "kb"))
        listing = svc.listing()
        # only a kb that lives in the bases dir is listed (and so can be active); a kb given by path (KB=<folder>,
        # the $KB_ROOT test fixture) is not, whatever the caller's env says
        listed = {os.path.realpath(r["root"]) for r in listing["kbs"]}
        if os.path.realpath(info["root"]) in listed:
            self.assertTrue(any(r["active"] for r in listing["kbs"]))
        self.assertNotIn("registry", listing)
        self.assertNotIn("legacy", info)

    def test_git_ceiling_never_hides_the_engines_own_repo(self):
        ceilings = {os.path.realpath(p) for p in os.environ["GIT_CEILING_DIRECTORIES"].split(os.pathsep) if p}
        self.assertNotIn(os.path.realpath(kbconfig.checkout_root()), ceilings)
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=os.path.join(kbconfig.checkout_root(), "src"),
                             capture_output=True, text=True, check=False)
        self.assertEqual(os.path.realpath(top.stdout.strip()), os.path.realpath(kbconfig.checkout_root()), top.stderr)

    def test_git_state_of_a_plain_folder_never_walks_up(self):
        from kb_distillery.services.kb import git_state
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(git_state(d)["repo"], False)


class KbFlag(unittest.TestCase):
    def test_dash_dash_kb_is_consumed_from_argv(self):
        code = ("import sys; sys.argv += ['--kb', 'nope', 'status']; import os; os.environ.pop('KB', None); "
                "import kb_distillery.kbconfig as k; print(sys.argv[1:], os.environ.get('KB'), k._ARGV_KB)")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env=dict(os.environ, PYTHONPATH=os.path.join(kbconfig.checkout_root(), "src")))
        self.assertEqual(out.stdout.strip(), "['status'] nope nope", out.stderr)


class SuiteIsolation(unittest.TestCase):
    def test_an_unselected_run_never_sees_the_real_bases_dir(self):
        if os.environ.get("KB") or not os.environ.get("KB_ROOT", "").endswith("kb-fixture"):
            return          # the caller picked a kb on purpose; the fixture isolation does not apply
        self.assertNotEqual(os.path.realpath(kbconfig.bases_dir()), os.path.realpath(os.path.expanduser("~/knowledge")))
        self.assertEqual(kbconfig.discover(), {})



if __name__ == "__main__":
    unittest.main()
