"""kb_distillery.config.kb (discovery, kb.toml, selection) and kb_distillery.vault.kbtypes ([types] → the schema constants)."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.config import kb as kbconfig
from kb_distillery.vault import kbtypes as types


def _write(root, text):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "kb.toml"), "w", encoding="utf-8") as f:
        f.write(text)


def _sh(cwd, *args):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


MINIMAL = '[kb]\nid = "demo"\nname = "Demo"\nschema_version = "1.5"\n'


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
        _write(os.path.join(self.bases, "old"), MINIMAL.replace('"demo"', '"old"').replace("1.5", "0.9"))
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
    """The primary working tree is found from a linked worktree; hooks point into it (it outlives the worktree)."""

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

    def at(self, root):
        return patch.object(kbconfig, "checkout_root", lambda: root)

    def test_main_checkout_is_its_own_primary(self):
        with self.at(self.main):
            self.assertEqual(kbconfig.primary_root(), self.main)

    def test_linked_worktree_finds_the_main_checkout(self):
        with self.at(self.work):
            self.assertEqual(kbconfig.primary_root(), self.main)

    def test_no_git_at_all_falls_back_to_the_checkout(self):
        plain = os.path.join(self.tmp, "export")
        os.makedirs(plain)
        with self.at(plain):
            self.assertEqual(kbconfig.primary_root(), plain)

    def test_an_installed_package_has_no_primary_root(self):
        with self.at(None):
            self.assertIsNone(kbconfig.primary_root())

    KIT = os.path.join("src", "kb_distillery", "kits", "base", "hooks")

    def test_hooks_path_is_relative_inside_the_engine_and_absolute_elsewhere(self):
        with self.at(self.work):
            inside = os.path.join(self.main, "kbs", "thesis")
            os.makedirs(inside)
            self.assertEqual(kbconfig.hooks_path_for(inside), os.path.join("..", "..", self.KIT))
            deeper = os.path.join(self.main, "examples", "demo")
            os.makedirs(deeper)
            self.assertEqual(kbconfig.hooks_path_for(deeper), os.path.join("..", "..", self.KIT))
            outside = os.path.join(self.tmp, "elsewhere", "notes")
            os.makedirs(outside)
            self.assertEqual(kbconfig.hooks_path_for(outside), os.path.join(self.main, self.KIT))

    def test_hooks_path_from_the_primary_itself_is_its_own_kit(self):
        with self.at(self.main):
            inside = os.path.join(self.main, "kbs", "thesis")
            os.makedirs(inside)
            self.assertEqual(kbconfig.hooks_path_for(inside), os.path.join("..", "..", self.KIT))

    def test_hooks_path_of_an_installed_package_is_the_packaged_kit(self):
        from kb_distillery.config import resources
        with patch.object(resources, "repo_root", lambda: None):
            path = kbconfig.hooks_path_for(os.path.join(self.tmp, "notes"))
        self.assertTrue(os.path.isabs(path))
        self.assertTrue(path.endswith(os.path.join("kits", "base", "hooks")), path)
        self.assertEqual(os.path.realpath(path), os.path.realpath(str(resources.resource("kits/base/hooks"))))


class BasesDir(unittest.TestCase):
    """bases_dir() = $KB_DISTILLERY_HOME or ~/knowledge; a checkout's own kbs/ is not searched."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.home = os.path.join(self.tmp, "home")
        self.main = os.path.join(self.tmp, "engine")
        self.work = os.path.join(self.tmp, "wt")
        os.makedirs(self.main)
        _sh(self.main, "init", "-q", "-b", "main")
        _sh(self.main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init")
        _sh(self.main, "worktree", "add", "-q", "-b", "x", self.work)
        self.env = patch.dict(os.environ, {"HOME": self.tmp})
        self.env.start()
        for k in ("KB_BASES_DIR", "KB_DISTILLERY_HOME", "KB", "KB_ROOT"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def at(self, root):
        return patch.object(kbconfig, "checkout_root", lambda: root)

    def test_default_is_knowledge_in_the_home_folder(self):
        self.assertEqual(kbconfig.bases_dir(), os.path.join(self.tmp, "knowledge"))

    def test_home_variable_replaces_it_and_expands_a_tilde(self):
        with patch.dict(os.environ, {"KB_DISTILLERY_HOME": self.home}):
            self.assertEqual(kbconfig.bases_dir(), self.home)
        with patch.dict(os.environ, {"KB_DISTILLERY_HOME": "~/elsewhere"}):
            self.assertEqual(kbconfig.bases_dir(), os.path.join(self.tmp, "elsewhere"))

    def test_a_checkouts_own_kbs_folder_is_not_searched(self):
        """No repo fallback: an id that is not under the bases dir is unknown, from the primary and from a worktree."""
        _write(os.path.join(self.main, "kbs", "demo"), MINIMAL)
        _write(os.path.join(self.work, "kbs", "demo"), MINIMAL)
        os.makedirs(self.home)
        for root in (self.main, self.work):
            with patch.dict(os.environ, {"KB_DISTILLERY_HOME": self.home}), self.at(root):
                self.assertEqual(kbconfig.search_dirs(), [self.home])
                self.assertEqual(kbconfig.discover(), {})
                with self.assertRaises(kbconfig.KbConfigError):
                    kbconfig.load("demo")

    def test_the_home_folder_is_where_ids_resolve(self):
        _write(os.path.join(self.home, "demo"), MINIMAL.replace("Demo", "In home"))
        _write(os.path.join(self.main, "kbs", "demo"), MINIMAL)
        with patch.dict(os.environ, {"KB_DISTILLERY_HOME": self.home}), self.at(self.work):
            self.assertEqual(kbconfig.load("demo").name, "In home")

    def test_bases_dir_override_is_exclusive(self):
        os.makedirs(self.home)
        with patch.dict(os.environ, {"KB_BASES_DIR": self.home}), self.at(self.main):
            self.assertEqual(kbconfig.search_dirs(), [self.home])

    def test_an_installed_package_searches_the_home_folder_only(self):
        with patch.dict(os.environ, {"KB_DISTILLERY_HOME": self.home}), self.at(None):
            self.assertEqual(kbconfig.search_dirs(), [self.home])

    def test_think_is_searched_in_the_bases_dir_only(self):
        os.makedirs(os.path.join(self.main, "kbs", "think"))
        with patch.dict(os.environ, {"KB_DISTILLERY_HOME": self.home}), self.at(self.main):
            self.assertEqual(kbconfig.think_root(), os.path.join(self.home, "think"))
            os.makedirs(os.path.join(self.home, "think"))
            self.assertEqual(kbconfig.think_root(), os.path.join(self.home, "think"))


class UpwardDiscovery(unittest.TestCase):
    """Inside a kb folder (outside the engine checkout) no KB / --kb is needed."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.kb = os.path.join(self.tmp, "notes")
        _write(self.kb, MINIMAL.replace('"demo"', '"notes"'))
        os.makedirs(os.path.join(self.kb, "wiki", "deep"))
        self.env = patch.dict(os.environ, {"KB_BASES_DIR": os.path.join(self.tmp, "none")})
        self.env.start()
        for k in ("KB", "KB_ROOT"):
            os.environ.pop(k, None)
        self.old = os.getcwd()

    def tearDown(self):
        os.chdir(self.old)
        self.env.stop()

    def test_the_nearest_kb_toml_above_the_current_folder_is_selected(self):
        os.chdir(os.path.join(self.kb, "wiki", "deep"))
        self.assertEqual(kbconfig.kb_above(), self.kb)
        with patch.object(kbconfig, "_ARGV_KB", None):
            self.assertEqual(kbconfig.selected(), self.kb)

    def test_env_and_flag_win_over_the_folder(self):
        os.chdir(self.kb)
        with patch.dict(os.environ, {"KB": "other"}):
            self.assertEqual(kbconfig.selected(), "other")

    def test_a_folder_without_a_kb_above_it_selects_nothing(self):
        os.makedirs(os.path.join(self.tmp, "empty"))
        os.chdir(os.path.join(self.tmp, "empty"))
        self.assertIsNone(kbconfig.kb_above())

    def test_inside_the_engine_checkout_nothing_is_discovered(self):
        os.chdir(self.kb)
        with patch.object(kbconfig, "checkout_root", lambda: self.tmp):
            self.assertIsNone(kbconfig.kb_above())


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


class RelativeKbPath(unittest.TestCase):
    """`KB=./examples/demo` is resolved once, against the folder the process started in, and exported absolute."""

    def test_relative_kb_is_anchored_at_import_and_survives_a_cwd_change(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.realpath(os.path.join(d, "kbs", "mine"))
            os.makedirs(folder)
            code = ("import os, sys; from kb_distillery.config import kb as kbconfig; os.chdir('/'); "
                    "print(os.environ['KB']); print(kbconfig.selected())")
            env = {**os.environ, "KB": "./kbs/mine"}
            env.pop("KB_ROOT", None)
            out = subprocess.run([sys.executable, "-c", code], cwd=os.path.realpath(d), env=env, capture_output=True,
                                 text=True, check=True).stdout.split()
            self.assertEqual(out, [folder, folder])

    def test_a_kb_id_is_left_alone(self):
        env = {**os.environ, "KB": "demo"}
        out = subprocess.run([sys.executable, "-c", "import os; from kb_distillery.config import kb as kbconfig; print(os.environ['KB'])"],
                             env=env, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, "demo")



if __name__ == "__main__":
    unittest.main()
