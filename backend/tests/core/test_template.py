"""Ontology templates: a kb names one, extends it, and cannot edit it. Needs no kb content."""
import os
import tempfile
import unittest
from unittest.mock import patch

from kb import kbconfig
from kb.core import kbtypes, template
from kb.services.cypher import edge_config

SCHEMA = "%d.%d" % kbconfig.SCHEMA_VERSION

TEMPLATE = """\
[template]
name = "research"
version = 1
description = "test template"

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


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.templates = os.path.join(self.tmp.name, "templates")
        write(os.path.join(self.templates, "research", "template.toml"), TEMPLATE)
        env = patch.dict(os.environ, {"KB_TEMPLATES_DIR": self.templates})
        env.start()
        self.addCleanup(env.stop)

    def kb(self, extra="", template_name="research"):
        root = os.path.join(self.tmp.name, "kbs", "x")
        head = f'[kb]\nid = "x"\nname = "X"\nschema_version = "{SCHEMA}"\n'
        if template_name:
            head += f'template = "{template_name}"\n'
        write(os.path.join(root, "kb.toml"), head + extra)
        return kbconfig.load_dir(root)

    def test_a_kb_gets_the_templates_types_and_edges(self):
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

    def test_restating_a_template_value_is_fine(self):
        cfg = self.kb('[types.source.paper]\nlabel = "Paper"\n\n[edges]\ntypes = ["extends"]\n')
        self.assertEqual(set(kbtypes.load(cfg).source_types), {"paper"})

    def test_editing_a_template_value_is_refused_naming_table_and_key(self):
        cfg = self.kb('[types.source.paper]\nlabel = "Article"\n')
        with self.assertRaises(template.TemplateError) as cm:
            kbtypes.load(cfg)
        msg = str(cm.exception)
        self.assertIn("[types].source.paper.label", msg)
        self.assertIn("not edit it", msg)

    def test_a_kb_without_a_template_reads_only_its_own_tables(self):
        cfg = self.kb('[types.source.note]\nlabel = "Note"\n', template_name="")
        self.assertEqual(cfg.template, "")
        self.assertEqual(set(kbtypes.load(cfg).source_types), {"note"})
        self.assertEqual(edge_config(cfg)["types"], [])

    def test_an_unknown_template_is_a_config_error_at_load(self):
        with self.assertRaises(kbconfig.KbConfigError) as cm:
            self.kb(template_name="nope")
        self.assertIn("research", str(cm.exception))             # names what is known

    def test_a_template_must_carry_its_own_folder_name_and_a_version(self):
        write(os.path.join(self.templates, "other", "template.toml"), '[template]\nname = "wrong"\nversion = 1\n')
        with self.assertRaises(template.TemplateError):
            template.load("other")

    def test_unreserved_tables_are_rejected_until_a_phase_gives_them_a_meaning(self):
        write(os.path.join(self.templates, "views", "template.toml"),
              '[template]\nname = "views"\nversion = 1\n\n[views]\nx = 1\n')
        with self.assertRaises(template.TemplateError) as cm:
            template.load("views")
        self.assertIn("views", str(cm.exception))

    def test_a_template_change_is_seen_without_a_restart(self):
        self.assertEqual(template.version("research"), 1)
        write(os.path.join(self.templates, "research", "template.toml"), TEMPLATE.replace("version = 1", "version = 2"))
        os.utime(template.path_of("research"), ns=(1, 2 ** 40))
        self.assertEqual(template.version("research"), 2)

    def test_names_lists_the_templates(self):
        self.assertEqual(template.names(), ["research"])


if __name__ == "__main__":
    unittest.main()
