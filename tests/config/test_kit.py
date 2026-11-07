"""Kits: a kb names one, extends it, and cannot edit it. Needs no kb content."""
import os
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import resources
from kb_distillery.vault import kbtypes
from kb_distillery.config import kit
from kb_distillery.graph.model import edge_config

SCHEMA = "%d.%d" % kbconfig.SCHEMA_VERSION

KIT = """\
[kit]
name = "research"
version = 1
description = "test kit"

[types]
areas = ["statistics", "quantum"]
source_fields = ["authors"]

[types.source.paper]
label = "Paper"
prefix = "paper-"
yeared = true

[types.collection.book]
label = "Book"
kind = "partition"

[types.concept.idea]
label = "Idea"
prefix = ""

[edges]
types = ["extends", "uses", "contradicts"]
symmetric = ["contradicts"]
note_required = ["contradicts"]
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class KitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.kits = os.path.join(self.tmp.name, "kits")
        write(os.path.join(self.kits, "research", "kit.toml"), KIT)
        env = patch.dict(os.environ, {"KB_KITS_DIR": self.kits})
        env.start()
        self.addCleanup(env.stop)

    def kb(self, extra="", kit_name="research"):
        root = os.path.join(self.tmp.name, "kbs", "x")
        head = f'[kb]\nid = "x"\nname = "X"\nschema_version = "{SCHEMA}"\n'
        if kit_name:
            head += f'kit = "{kit_name}"\n'
        write(os.path.join(root, "kb.toml"), head + extra)
        return kbconfig.load_dir(root)

    def test_a_kb_gets_the_kits_types_and_edges(self):
        cfg = self.kb()
        t = kbtypes.load(cfg)
        self.assertEqual(set(t.source_types), {"paper"})
        self.assertEqual(set(t.concept_types), {"idea"})
        self.assertEqual(set(t.areas), {"statistics", "quantum"})
        edges = edge_config(cfg)
        self.assertEqual(edges["types"], ["contradicts", "extends", "uses"])
        self.assertEqual(edges["note_required"], {"contradicts"})
        self.assertIn("CONTRADICTS", edges["symmetric"])

    def test_a_kb_can_add_types_areas_and_edges(self):
        cfg = self.kb('[types]\nareas = ["optimization-theory"]\n\n[types.source.video]\nlabel = "Video"\n'
                      '\n[edges]\ntypes = ["addresses"]\n')
        t = kbtypes.load(cfg)
        self.assertEqual(set(t.source_types), {"paper", "video"})
        self.assertEqual(list(t.areas) and sorted(t.areas), ["optimization-theory", "quantum", "statistics"])
        self.assertEqual(edge_config(cfg)["types"], ["addresses", "contradicts", "extends", "uses"])

    def test_restating_a_kit_value_is_fine(self):
        cfg = self.kb('[types.source.paper]\nlabel = "Paper"\n\n[edges]\ntypes = ["extends"]\n')
        self.assertEqual(set(kbtypes.load(cfg).source_types), {"paper"})

    def test_editing_a_kit_value_is_refused_naming_table_and_key(self):
        cfg = self.kb('[types.source.paper]\nlabel = "Article"\n')
        with self.assertRaises(kit.KitError) as cm:
            kbtypes.load(cfg)
        msg = str(cm.exception)
        self.assertIn("[types].source.paper.label", msg)
        self.assertIn("not edit it", msg)

    def test_a_kb_without_a_kit_reads_only_its_own_tables(self):
        cfg = self.kb('[types.source.note]\nlabel = "Note"\n', kit_name="")
        self.assertEqual(cfg.kit, "")
        self.assertEqual(set(kbtypes.load(cfg).source_types), {"note"})
        self.assertEqual(edge_config(cfg)["types"], [])

    def test_an_unknown_kit_is_a_config_error_at_load(self):
        with self.assertRaises(kbconfig.KbConfigError) as cm:
            self.kb(kit_name="nope")
        self.assertIn("research", str(cm.exception))             # names what is known

    def test_a_kit_must_carry_its_own_folder_name_and_a_version(self):
        write(os.path.join(self.kits, "other", "kit.toml"), '[kit]\nname = "wrong"\nversion = 1\n')
        with self.assertRaises(kit.KitError):
            kit.load("other")

    def test_unreserved_tables_are_rejected_until_a_phase_gives_them_a_meaning(self):
        write(os.path.join(self.kits, "views", "kit.toml"),
              '[kit]\nname = "views"\nversion = 1\n\n[views]\nx = 1\n')
        with self.assertRaises(kit.KitError) as cm:
            kit.load("views")
        self.assertIn("views", str(cm.exception))

    def test_a_kit_change_is_seen_without_a_restart(self):
        self.assertEqual(kit.version("research"), 1)
        write(os.path.join(self.kits, "research", "kit.toml"), KIT.replace("version = 1", "version = 2"))
        os.utime(kit.path_of("research"), ns=(1, 2 ** 40))
        self.assertEqual(kit.version("research"), 2)

    def test_names_lists_the_kits(self):
        self.assertEqual(kit.names(), ["research"])

    def test_a_kb_names_its_kit_with_kit_or_the_older_template_key(self):
        self.assertEqual(self.kb().kit, "research")
        root = os.path.join(self.tmp.name, "kbs", "t")
        write(os.path.join(root, "kb.toml"), f'[kb]\nid = "t"\nname = "T"\nschema_version = "{SCHEMA}"\ntemplate = "research"\n')
        cfg = kbconfig.load_dir(root)
        self.assertEqual(cfg.kit, "research")
        self.assertEqual(set(kbtypes.load(cfg).source_types), {"paper"})

    def test_naming_two_different_kits_is_refused(self):
        write(os.path.join(self.kits, "other", "kit.toml"), '[kit]\nname = "other"\nversion = 1\n')
        root = os.path.join(self.tmp.name, "kbs", "both")
        write(os.path.join(root, "kb.toml"), f'[kb]\nid = "both"\nname = "B"\nschema_version = "{SCHEMA}"\n'
                                              'kit = "research"\ntemplate = "other"\n')
        with self.assertRaises(kbconfig.KbConfigError) as cm:
            kbconfig.load_dir(root)
        self.assertIn("different kits", str(cm.exception))

    def test_extends_builds_a_chain_root_first_and_must_name_a_known_kit(self):
        write(os.path.join(self.kits, "child", "kit.toml"), '[kit]\nname = "child"\nversion = 1\nextends = "research"\n')
        self.assertEqual(kit.chain("child"), ["research", "child"])
        self.assertEqual(kit.chain("research"), ["research"])
        write(os.path.join(self.kits, "orphan", "kit.toml"), '[kit]\nname = "orphan"\nversion = 1\nextends = "missing"\n')
        with self.assertRaises(kit.KitError) as cm:
            kit.chain("orphan")
        self.assertIn("missing", str(cm.exception))
        with self.assertRaises(kbconfig.KbConfigError):                  # a kb naming it fails at load, not at first use
            self.kb(kit_name="orphan")

    def test_extends_does_not_merge_the_parents_types_into_the_child(self):
        write(os.path.join(self.kits, "child", "kit.toml"),
              '[kit]\nname = "child"\nversion = 1\nextends = "research"\n\n[types.source.video]\nlabel = "Video"\n')
        self.assertEqual(set(kbtypes.load(self.kb(kit_name="child")).source_types), {"video"})

    def test_a_cycle_in_extends_is_refused(self):
        write(os.path.join(self.kits, "a", "kit.toml"), '[kit]\nname = "a"\nversion = 1\nextends = "b"\n')
        write(os.path.join(self.kits, "b", "kit.toml"), '[kit]\nname = "b"\nversion = 1\nextends = "a"\n')
        with self.assertRaises(kit.KitError) as cm:
            kit.chain("a")
        self.assertIn("extends itself", str(cm.exception))

    def test_extends_must_be_a_kit_name(self):
        write(os.path.join(self.kits, "bad", "kit.toml"), '[kit]\nname = "bad"\nversion = 1\nextends = "../x"\n')
        with self.assertRaises(kit.KitError):
            kit.load("bad")

    def test_the_kits_dir_is_the_env_override_else_the_package_folder(self):
        self.assertEqual(kit.kits_dir(), self.kits)
        with patch.dict(os.environ):
            os.environ.pop("KB_KITS_DIR")
            self.assertEqual(kit.kits_dir(), str(resources.resource("kits")))
            self.assertEqual(kit.names(), ["base", "research"])


class ShippedKits(unittest.TestCase):
    """The kits that ship in the package, with no override: the old names still resolve, and nothing else changed."""

    def setUp(self):
        env = patch.dict(os.environ)
        env.start()
        os.environ.pop("KB_KITS_DIR", None)
        self.addCleanup(env.stop)

    def test_base_and_research_ship_and_research_extends_base(self):
        self.assertEqual(kit.names(), ["base", "research"])
        self.assertEqual(kit.chain("research"), ["base", "research"])
        self.assertEqual(kit.load("research")["kit"]["extends"], "base")

    def test_the_old_template_names_resolve_to_the_kits(self):
        self.assertEqual((kit.canonical("starter"), kit.canonical("academic-research")), ("base", "research"))
        self.assertTrue(kit.exists("starter") and kit.exists("academic-research"))
        self.assertEqual(kit.load("academic-research")["kit"]["name"], "research")
        self.assertFalse(kit.exists("nope") or kit.exists("") or kit.exists("../base"))

    def test_the_kit_and_template_keys_read_the_same_kit(self):
        for key, value, want in (("kit", "base", "base"), ("template", "starter", "base"), ("template", "academic-research", "research")):
            with tempfile.TemporaryDirectory() as tmp:
                root = os.path.join(tmp, "kbs", "x")
                write(os.path.join(root, "kb.toml"), f'[kb]\nid = "x"\nname = "X"\nschema_version = "{SCHEMA}"\n{key} = "{value}"\n')
                self.assertEqual(kbconfig.load_dir(root).kit, want)

    def test_defaults_ship_beside_the_base_kit(self):
        base = resources.resource("kits/base")
        for rel in ("kit.toml", "defaults/flags.toml", "defaults/docs/kits.md", "defaults/templates/paper.md",
                    "defaults/digest/focus.md"):
            self.assertTrue((base / rel).is_file(), rel)


if __name__ == "__main__":
    unittest.main()


def test_base_kit_lists_the_chat_agent_skills():
    from kb_distillery.config import kit
    assert kit.load("base")["agent"]["skills"] == ["deep-research"]


def test_kit_agent_table_is_validated(tmp_path, monkeypatch):
    import pytest
    from kb_distillery.config import kit
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "kit.toml").write_text('[kit]\nname = "bad"\nversion = 1\n[agent]\nskills = "deep-research"\n')
    monkeypatch.setenv("KB_KITS_DIR", str(tmp_path))
    kit.load.cache_clear() if hasattr(kit.load, "cache_clear") else None
    with pytest.raises(kit.KitError, match="skills must be a list"):
        kit.load("bad")


class ReadyViewsTest(unittest.TestCase):
    def test_base_ships_its_views_and_research_adds_to_them(self):
        base = {v["id"]: v for v in kit.views("base")}
        for vid in ("contradictions", "orphans", "hubs", "by-type", "recent-additions", "gaps",
                    "open-contradictions", "frontier", "quiet-hubs", "neighborhood"):
            self.assertIn(vid, base)
        research = kit.views("research")
        ids = [v["id"] for v in research]
        self.assertTrue(set(base) <= set(ids))
        self.assertIn("open-questions", ids)
        self.assertEqual({v["kit"] for v in research}, {"base", "research"})
        for v in research:
            self.assertTrue(v["layers"] and v["name"] and v["description"])

    def test_a_child_view_replaces_the_parent_one_with_the_same_id(self):
        with tempfile.TemporaryDirectory() as d:
            for name, extra in (("base", ""), ("kid", 'extends = "base"\n')):
                os.makedirs(os.path.join(d, name, "views"))
                with open(os.path.join(d, name, "kit.toml"), "w") as f:
                    f.write(f'[kit]\nname = "{name}"\nversion = 1\n{extra}')
            with open(os.path.join(d, "base", "views", "v.toml"), "w") as f:
                f.write('[[view]]\nid = "a"\nname = "A"\ndescription = "one"\nlayers = ["show nodes all"]\n')
            with open(os.path.join(d, "kid", "views", "v.toml"), "w") as f:
                f.write('[[view]]\nid = "a"\nname = "A2"\ndescription = "two"\nlayers = ["hide nodes all"]\n')
            with patch.dict(os.environ, {kit.KITS_DIR_ENV: d}):
                got = kit.views("kid")
        self.assertEqual([(v["id"], v["name"], v["kit"]) for v in got], [("a", "A2", "kid")])

    def test_a_malformed_view_names_the_file_and_key(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "base", "views"))
            with open(os.path.join(d, "base", "kit.toml"), "w") as f:
                f.write('[kit]\nname = "base"\nversion = 1\n')
            with open(os.path.join(d, "base", "views", "v.toml"), "w") as f:
                f.write('[[view]]\nid = "a"\nname = "A"\ndescription = "one"\nlayers = []\n')
            with patch.dict(os.environ, {kit.KITS_DIR_ENV: d}):
                with self.assertRaisesRegex(kit.KitError, "v.toml.*layers"):
                    kit.views("base")
