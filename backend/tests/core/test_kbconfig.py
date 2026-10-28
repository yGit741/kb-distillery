"""kb.kbconfig (discovery, kb.toml, selection) and kb.core.kbtypes ([types] → the schema constants)."""
import os
import tempfile
import unittest
from unittest.mock import patch

from kb import kbconfig
from kb.core import kbtypes as types


def _write(root, text):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "kb.toml"), "w", encoding="utf-8") as f:
        f.write(text)


MINIMAL = '[kb]\nid = "demo"\nname = "Demo"\nschema_version = "1.3"\n'


class Discovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bases = os.path.join(self.tmp, "knowledge-bases")
        _write(os.path.join(self.bases, "kb-demo"), MINIMAL)
        os.makedirs(os.path.join(self.bases, "kb-noconfig"))          # a folder without kb.toml is not a kb
        os.makedirs(os.path.join(self.bases, "think"))
        self.env = patch.dict(os.environ, {"KB_BASES_DIR": self.bases}, clear=False)
        self.env.start()
        for k in ("KB", "KB_ROOT"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def test_folders_named_kb_dash_with_a_config_are_knowledge_bases(self):
        self.assertEqual(list(kbconfig.discover()), ["demo"])
        self.assertEqual(kbconfig.discover()["demo"], os.path.realpath(os.path.join(self.bases, "kb-demo")))

    def test_registry_links_a_folder_anywhere_and_names_a_default(self):
        elsewhere = os.path.join(self.tmp, "somewhere", "my-notes")
        _write(elsewhere, MINIMAL.replace('"demo"', '"linked"'))
        reg = os.path.join(self.tmp, "knowledge-bases.toml")
        with open(reg, "w", encoding="utf-8") as f:
            f.write(f'default = "linked"\n[[kb]]\nid = "linked"\npath = "{elsewhere}"\n')
        with patch.object(kbconfig, "registry_path", return_value=reg):
            found = kbconfig.discover()
            self.assertEqual(found["linked"], os.path.realpath(elsewhere))
            self.assertEqual(kbconfig.selected_id(), "linked")

    def test_selection_order_argv_env_then_the_only_kb(self):
        self.assertEqual(kbconfig.selected_id(), "demo")                         # the only one
        with patch.dict(os.environ, {"KB": "other"}):
            self.assertEqual(kbconfig.selected_id(), "other")
            with patch.object(kbconfig, "_ARGV_KB", "argv-wins"):     # `--kb` is consumed from argv at import
                self.assertEqual(kbconfig.selected_id(), "argv-wins")
        _write(os.path.join(self.bases, "kb-two"), MINIMAL.replace('"demo"', '"two"'))
        self.assertIsNone(kbconfig.selected_id())                                # two kbs, nothing decides

    def test_git_root_is_the_folder_when_it_is_a_repo(self):
        cfg = kbconfig.load("demo")
        self.assertIsNone(cfg.git_root)
        os.makedirs(os.path.join(self.bases, "kb-demo", ".git"))
        self.assertEqual(kbconfig.load("demo").git_root, cfg.root)

    def test_bad_configs_name_the_problem(self):
        _write(os.path.join(self.bases, "kb-bad"), '[kb]\nid = "bad"\nname = "Bad"\n')
        with self.assertRaisesRegex(kbconfig.KbConfigError, "schema_version is required"):
            kbconfig.load("bad")
        _write(os.path.join(self.bases, "kb-old"), MINIMAL.replace('"demo"', '"old"').replace("1.3", "0.9"))
        with self.assertRaisesRegex(kbconfig.KbConfigError, "schema_version 0.9"):
            kbconfig.load("old")
        _write(os.path.join(self.bases, "kb-mismatch"), MINIMAL)                  # folder says mismatch, file says demo
        with self.assertRaisesRegex(kbconfig.KbConfigError, "calls it 'mismatch'"):
            kbconfig.load("mismatch")
        with self.assertRaisesRegex(kbconfig.KbConfigError, "no knowledge base 'nope'"):
            kbconfig.load("nope")


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
