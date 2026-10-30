"""kb.kbconfig (discovery, kb.toml, selection) and kb.core.kbtypes ([types] → the schema constants)."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb import kbconfig
from kb.core import kbtypes as types


def _write(root, text):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "kb.toml"), "w", encoding="utf-8") as f:
        f.write(text)


def _sh(cwd, *args):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


MINIMAL = '[kb]\nid = "demo"\nname = "Demo"\nschema_version = "1.3"\n'


class Discovery(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.bases = os.path.join(self.tmp, "kbs")
        _write(os.path.join(self.bases, "demo"), MINIMAL)
        os.makedirs(os.path.join(self.bases, "noconfig"))             # a folder without kb.toml is not a kb
        os.makedirs(os.path.join(self.bases, "think"))                # think has no kb.toml: never listed
        self.env = patch.dict(os.environ, {"KB_BASES_DIR": self.bases}, clear=False)
        self.env.start()
        for k in ("KB", "KB_ROOT"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def test_folders_with_a_config_are_knowledge_bases_and_the_folder_name_is_the_id(self):
        self.assertEqual(list(kbconfig.discover()), ["demo"])
        self.assertEqual(kbconfig.discover()["demo"], os.path.join(self.bases, "demo"))

    def test_there_is_no_registry_and_no_kb_prefix(self):
        for gone in ("register", "registry_path", "_read_registry", "FOLDER_PREFIX", "REGISTRY_NAME"):
            self.assertFalse(hasattr(kbconfig, gone), gone)
        _write(os.path.join(self.bases, "kb-old-style"), MINIMAL.replace('"demo"', '"kb-old-style"'))
        self.assertIn("kb-old-style", kbconfig.discover())            # just a folder name now

    def test_selection_order_argv_env_then_the_only_kb(self):
        self.assertEqual(kbconfig.selected(), "demo")                              # the only one
        with patch.dict(os.environ, {"KB": "other"}):
            self.assertEqual(kbconfig.selected(), "other")
            with patch.object(kbconfig, "_ARGV_KB", "argv-wins"):         # `--kb` is consumed from argv at import
                self.assertEqual(kbconfig.selected(), "argv-wins")
        _write(os.path.join(self.bases, "two"), MINIMAL.replace('"demo"', '"two"'))
        self.assertIsNone(kbconfig.selected())                                     # two kbs, nothing decides

    def test_git_root_is_the_folder_when_it_is_a_repo(self):
        cfg = kbconfig.load("demo")
        self.assertIsNone(cfg.git_root)
        os.makedirs(os.path.join(self.bases, "demo", ".git"))
        self.assertEqual(kbconfig.load("demo").git_root, cfg.root)

    def test_bad_configs_name_the_problem(self):
        _write(os.path.join(self.bases, "bad"), '[kb]\nid = "bad"\nname = "Bad"\n')
        with self.assertRaisesRegex(kbconfig.KbConfigError, "schema_version is required"):
            kbconfig.load("bad")
        _write(os.path.join(self.bases, "old"), MINIMAL.replace('"demo"', '"old"').replace("1.3", "0.9"))
        with self.assertRaisesRegex(kbconfig.KbConfigError, "schema_version 0.9"):
            kbconfig.load("old")
        _write(os.path.join(self.bases, "mismatch"), MINIMAL)                     # folder says mismatch, file says demo
        with self.assertRaisesRegex(kbconfig.KbConfigError, "folder is named 'mismatch'"):
            kbconfig.load("mismatch")

    def test_unknown_id_lists_the_known_ones_and_points_at_paths(self):
        with self.assertRaisesRegex(kbconfig.KbConfigError, r"no knowledge base 'nope' \(known: demo.*--kb \./path"):
            kbconfig.load("nope")


class PathRefs(unittest.TestCase):
    """`--kb` / `$KB` take an id or a folder path."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.elsewhere = os.path.join(self.tmp, "somewhere", "my-notes")      # folder name ≠ id: fine by path
        _write(self.elsewhere, MINIMAL.replace('"demo"', '"mine"'))
        self.env = patch.dict(os.environ, {"KB_BASES_DIR": os.path.join(self.tmp, "kbs")}, clear=False)
        self.env.start()
        for k in ("KB", "KB_ROOT"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def test_which_values_are_paths(self):
        for ref in ("./x", "../x", "/abs/x", "~/x", "dir/x"):
            self.assertTrue(kbconfig.looks_like_path(ref), ref)
        for ref in ("demo", "yonatan-thesis", "kb-x"):
            self.assertFalse(kbconfig.looks_like_path(ref), ref)

    def test_absolute_relative_and_home_paths_load(self):
        self.assertEqual(kbconfig.load(self.elsewhere).id, "mine")
        old = os.getcwd()
        try:
            os.chdir(os.path.join(self.tmp, "somewhere"))
            self.assertEqual(kbconfig.load("./my-notes").root, self.elsewhere)
        finally:
            os.chdir(old)
        with patch.dict(os.environ, {"HOME": self.tmp}):
            self.assertEqual(kbconfig.load("~/somewhere/my-notes").root, self.elsewhere)

    def test_a_folder_that_is_not_a_kb_is_refused_by_name(self):
        with self.assertRaisesRegex(kbconfig.KbConfigError, "not a knowledge base folder"):
            kbconfig.load(self.tmp)

    def test_a_bare_id_is_never_taken_for_a_folder_in_the_cwd(self):
        old = os.getcwd()
        try:
            os.chdir(os.path.join(self.tmp, "somewhere"))
            with self.assertRaisesRegex(kbconfig.KbConfigError, "no knowledge base 'my-notes'"):
                kbconfig.load("my-notes")
        finally:
            os.chdir(old)

    def test_argv_path_is_made_absolute_and_exported(self):
        old = os.getcwd()
        try:
            os.chdir(os.path.join(self.tmp, "somewhere"))
            with patch.object(sys, "argv", ["prog", "--kb", "./my-notes", "lint"]), patch.dict(os.environ):
                self.assertEqual(kbconfig._consume_argv_kb(), self.elsewhere)
                self.assertEqual(os.environ["KB"], self.elsewhere)
                self.assertEqual(sys.argv, ["prog", "lint"])
        finally:
            os.chdir(old)


class PrimaryRoot(unittest.TestCase):
    """`kbs/` is the main checkout's, also when the code runs from a linked worktree."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.main = os.path.join(self.tmp, "engine")
        os.makedirs(self.main)
        _sh(self.main, "init", "-q", "-b", "main")
        _sh(self.main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init")
        self.work = os.path.join(self.tmp, "wt")
        _sh(self.main, "worktree", "add", "-q", "-b", "x", self.work)
        self.env = patch.dict(os.environ)
        self.env.start()
        os.environ.pop("KB_BASES_DIR", None)

    def tearDown(self):
        self.env.stop()

    def test_main_checkout_is_its_own_primary(self):
        with patch.object(kbconfig, "CHECKOUT_ROOT", self.main):
            self.assertEqual(kbconfig.primary_root(), self.main)
            self.assertEqual(kbconfig.bases_dir(), os.path.join(self.main, "kbs"))

    def test_linked_worktree_resolves_to_the_main_checkouts_kbs(self):
        with patch.object(kbconfig, "CHECKOUT_ROOT", self.work):
            self.assertEqual(kbconfig.primary_root(), self.main)
            self.assertEqual(kbconfig.bases_dir(), os.path.join(self.main, "kbs"))

    def test_no_git_at_all_falls_back_to_the_checkout(self):
        plain = os.path.join(self.tmp, "export")
        os.makedirs(plain)
        with patch.object(kbconfig, "CHECKOUT_ROOT", plain):
            self.assertEqual(kbconfig.primary_root(), plain)

    def test_hooks_path_is_relative_inside_kbs_and_absolute_elsewhere(self):
        with patch.object(kbconfig, "CHECKOUT_ROOT", self.work):
            inside = os.path.join(self.main, "kbs", "thesis")
            os.makedirs(inside)
            self.assertEqual(kbconfig.hooks_path_for(inside), "../../tools/kb-hooks")
            outside = os.path.join(self.tmp, "elsewhere", "notes")
            os.makedirs(outside)
            self.assertEqual(kbconfig.hooks_path_for(outside), os.path.join(self.main, "tools", "kb-hooks"))


class TypesFromConfig(unittest.TestCase):
    def test_defaults_are_the_explorer_type_set(self):
        t = types.build(None)
        self.assertEqual(t.source_types, frozenset({"paper", "part", "lecture", "article", "video", "mail", "ai-chat", "blog-post"}))
        self.assertEqual(t.partition_collections, frozenset({"book", "notebook"}))
        self.assertEqual(t.concept_types, frozenset({"idea", "topic", "question", "person"}))
        self.assertEqual(t.bare_types, {"idea", "person"})
        self.assertEqual(t.type_status["person"], set())
        self.assertEqual(t.type_status["paper"], types.READ_STATUS)
        self.assertEqual(t.type_status["idea"], types.GROW_STATUS)
        self.assertEqual(t.type_order[-2:], ("distilled-think", "scope"))
        self.assertEqual(set(t.type_color), set(t.layer_of))
        self.assertEqual(t.areas, frozenset())

    def test_a_layer_table_replaces_that_layers_defaults_and_keeps_the_others(self):
        t = types.build({
            "order": ["company", "book", "notebook", "course", "series", "paper", "part", "lecture", "article",
                      "video", "mail", "ai-chat", "blog-post"],
            "concept": {"company": {"label": "Company", "prefix": "company-", "status": ["new", "applied"]}},
        })
        self.assertEqual(t.concept_types, frozenset({"company"}))
        self.assertEqual(t.source_types, types.build(None).source_types)        # untouched layer keeps the defaults
        self.assertEqual(t.type_status["company"], {"new", "applied"})
        self.assertEqual(t.slug_prefix["company"], "company-")
        self.assertTrue(t.type_color["company"].startswith("#"))                # palette fallback
        self.assertEqual(t.layer_of["company"], "concept")
        self.assertEqual(t.layer_of["scope"], "collection")                     # tool-owned types always there

    def test_collection_kind_decides_partition_or_contents_and_prefix_defaults_to_the_name(self):
        t = types.build({"collection": {"album": {"label": "Album", "kind": "partition"}, "playlist": {"label": "Playlist"}}})
        self.assertEqual(t.partition_collections, frozenset({"album"}))
        self.assertEqual(t.contents_collections, frozenset({"playlist"}))
        self.assertEqual(t.slug_prefix["album"], "album-")

    def test_invalid_tables_are_refused_by_name(self):
        with self.assertRaisesRegex(types.TypesError, r"\[types.concept.x\] needs a `label`"):
            types.build({"concept": {"x": {}}})
        with self.assertRaisesRegex(types.TypesError, "defined twice"):
            types.build({"concept": {"paper": {"label": "Paper"}}})
        with self.assertRaisesRegex(types.TypesError, "order must list every type once"):
            types.build({"order": ["paper"]})
        with self.assertRaisesRegex(types.TypesError, "share a filename prefix"):
            types.build({"concept": {"a": {"label": "A", "prefix": "x-"}, "b": {"label": "B", "prefix": "x-"}}})


if __name__ == "__main__":
    unittest.main()
