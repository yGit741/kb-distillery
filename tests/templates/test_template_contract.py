"""Contract every shipped template (templates/<name>/template.toml) must meet, plus what academic-research defines."""
import os
import tempfile
import unittest

from kb_distillery import kbconfig
from kb_distillery.core import kbtypes, template
from kb_distillery.services.cypher import edge_config

SCHEMA = "%d.%d" % kbconfig.SCHEMA_VERSION


def kb_naming(tmp, name):
    root = os.path.join(tmp, "kbs", "x")
    os.makedirs(root)
    with open(os.path.join(root, "kb.toml"), "w") as f:
        f.write(f'[kb]\nid = "x"\nname = "X"\nschema_version = "{SCHEMA}"\ntemplate = "{name}"\n')
    return kbconfig.load_dir(root)


class EveryTemplate(unittest.TestCase):
    def test_there_are_templates_to_check(self):
        self.assertIn("academic-research", template.names())

    def test_each_template_loads_builds_types_and_reads_edges(self):
        for name in template.names():
            with self.subTest(template=name), tempfile.TemporaryDirectory() as tmp:
                data = template.load(name)                                  # name == folder, version, known tables only
                self.assertEqual(data["template"]["name"], name)
                cfg = kb_naming(tmp, name)
                types = kbtypes.load(cfg)                                   # a valid [types]: layers, prefixes, order
                self.assertTrue(types.source_types or types.concept_types)
                edges = edge_config(cfg)
                self.assertTrue(set(edges["note_required"]) <= set(edges["types"]))

    def test_a_kb_naming_the_template_and_nothing_else_equals_the_template(self):
        for name in template.names():
            with self.subTest(template=name), tempfile.TemporaryDirectory() as tmp:
                cfg = kb_naming(tmp, name)
                self.assertEqual(cfg.section("types"), template.load(name).get("types", {}))
                self.assertEqual(cfg.section("edges"), template.load(name).get("edges", {}))


class AcademicResearch(unittest.TestCase):
    """The thesis kb's ontology, as lifted into the template; a change here is a decision, not a drift."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = kb_naming(self.tmp.name, "academic-research")

    def test_types(self):
        t = kbtypes.load(self.cfg)
        self.assertEqual(set(t.source_types), {"paper", "part", "lecture", "article", "video", "mail", "ai-chat", "blog-post"})
        self.assertEqual(set(t.partition_collections), {"book", "notebook"})
        self.assertEqual(set(t.contents_collections), {"course", "series"})
        self.assertEqual(set(t.concept_types), {"topic", "idea", "question", "person"})
        self.assertEqual(len(t.type_order), 18)                              # 16 kb types + the two tool-owned

    def test_areas_are_the_kbs_own(self):
        """Each area needs a theme-<area> page, so a template that listed some would break lint for every kb."""
        self.assertEqual(set(kbtypes.load(self.cfg).areas), set())
        self.assertEqual(kbtypes.load(self.cfg).source_fields, ("authors", "venue", "arxiv-id"))

    def test_the_eight_relation_types(self):
        edges = edge_config(self.cfg)
        self.assertEqual(edges["types"], sorted(["extends", "uses", "contradicts", "example-of", "open-problem-in",
                                                 "addresses", "discusses", "student-of"]))
        self.assertEqual(edges["note_required"], {"contradicts"})
        self.assertIn("CONTRADICTS", edges["symmetric"])


class DemoFollowsStarter(unittest.TestCase):
    """examples/demo is built from the starter template and adds the job-search types on top."""

    def setUp(self):
        self.cfg = kbconfig.load_dir(os.path.join(kbconfig.checkout_root(), "examples", "demo"))

    def test_the_demo_names_the_starter(self):
        self.assertEqual(self.cfg.template, "starter")

    def test_it_has_the_starters_types_and_its_own(self):
        starter = set(kbtypes.build(template.load("starter")["types"]).layer_of)
        t = kbtypes.load(self.cfg)
        self.assertTrue(starter <= set(t.layer_of))
        self.assertTrue({"posting", "process", "company", "interview"} <= set(t.layer_of))

    def test_no_two_types_share_a_colour(self):
        colours = list(kbtypes.load(self.cfg).type_color.values())
        self.assertEqual(len(colours), len(set(colours)))


if __name__ == "__main__":
    unittest.main()
