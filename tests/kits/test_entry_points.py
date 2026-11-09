"""Kits and skills installed as packages: found through the `kb_distillery.kits` / `kb_distillery.skills` entry-point
groups. A fixture package on a temp sys.path stands in for a pip-installed one: no network, no install."""
import os
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from kb_distillery import init_kb
from kb_distillery.config import kit

KIT_TOML = textwrap.dedent("""\
    [kit]
    name = "recipes"
    version = 1
    extends = "base"
    description = "Recipes from a fixture package."

    [types.source.recipe]
    label = "Recipe"
    prefix = "recipe-"
    """)

SKILL_MD = textwrap.dedent("""\
    ---
    name: fixture-skill
    description: A skill from a fixture package.
    ---
    # fixture-skill
    """)


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class EntryPointExtensions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = self.tmp.name
        write(os.path.join(root, "fx_recipes", "__init__.py"))
        write(os.path.join(root, "fx_recipes", "kit", "__init__.py"))
        write(os.path.join(root, "fx_recipes", "kit", "kit.toml"), KIT_TOML)
        write(os.path.join(root, "fx_recipes", "kit", "skills", "plate", "SKILL.md"), SKILL_MD.replace("fixture-skill", "plate"))
        write(os.path.join(root, "fx_recipes", "skill", "__init__.py"))
        write(os.path.join(root, "fx_recipes", "skill", "SKILL.md"), SKILL_MD)
        write(os.path.join(root, "fx_recipes", "broken", "__init__.py"))       # no kit.toml: skipped
        sys.path.insert(0, root)
        self.addCleanup(sys.path.remove, root)
        eps = {
            kit.KITS_GROUP: {"recipes": "fx_recipes.kit", "base": "fx_recipes.kit", "nope": "fx_recipes.broken",
                             "ghost": "no_such_pkg_xyz.kit"},
            kit.SKILLS_GROUP: {"fixture-skill": "fx_recipes.skill:thing", "deep-research": "fx_recipes.skill"},
        }
        p = patch.object(kit, "_entry_points", lambda group: dict(eps.get(group, {})))
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(lambda: [sys.modules.pop(m) for m in list(sys.modules) if m.startswith("fx_recipes")])

    def test_installed_kit_is_known_and_loads(self):
        self.assertIn("recipes", kit.names())
        self.assertTrue(kit.exists("recipes"))
        self.assertEqual(kit.load("recipes")["kit"]["extends"], "base")
        self.assertEqual(kit.chain("recipes"), ["base", "recipes"])
        self.assertEqual(kit.path_of("recipes"), os.path.join(self.tmp.name, "fx_recipes", "kit", "kit.toml"))

    def test_broken_or_missing_packages_are_skipped(self):
        self.assertNotIn("nope", kit.names())
        self.assertNotIn("ghost", kit.names())
        self.assertFalse(kit.exists("nope"))

    def test_built_in_name_wins(self):
        self.assertEqual(kit.kit_dir("base"), os.path.join(kit.kits_dir(), "base"))
        self.assertEqual(kit.names().count("base"), 1)

    def test_kit_skills_are_copied_for_a_kb(self):
        sources = init_kb.skill_sources("recipes")
        self.assertEqual(sources["plate"], os.path.join(self.tmp.name, "fx_recipes", "kit", "skills", "plate"))

    def test_loose_skill_reaches_every_kit_but_never_replaces_a_built_in(self):
        for name in ("base", "recipes"):
            sources = init_kb.skill_sources(name)
            self.assertEqual(sources["fixture-skill"], os.path.join(self.tmp.name, "fx_recipes", "skill"))
        self.assertNotIn(self.tmp.name, init_kb.skill_sources("base")["deep-research"])

    def test_without_packages_nothing_changes(self):
        with patch.object(kit, "_entry_points", lambda group: {}):
            self.assertNotIn("recipes", kit.names())
            self.assertFalse(kit.exists("recipes"))
            self.assertEqual(kit.skill_dirs(), {})


if __name__ == "__main__":
    unittest.main()
