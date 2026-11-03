"""Page conventions (`[pages]`): kit chain and kb resolution, the shipped kits' values, and that every kit's
page skeletons write the heading the kit names."""
import glob
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import kit, pages, paths
from kb_distillery.config.resources import resource
from kb_distillery.migrations import takeaways_heading as migration

SCHEMA = "%d.%d" % kbconfig.SCHEMA_VERSION
HEADING = re.compile(r"^## (Takeaways.*)$", re.M)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def kb_at(root, kit_name="", extra=""):
    head = f'[kb]\nid = "{os.path.basename(root)}"\nname = "X"\nschema_version = "{SCHEMA}"\n'
    if kit_name:
        head += f'kit = "{kit_name}"\n'
    write(os.path.join(root, "kb.toml"), head + extra)
    return kbconfig.load_dir(root)


class ShippedKitsTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("KB_KITS_DIR", None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_engine_defaults_are_generic(self):
        self.assertEqual(pages.DEFAULTS, {"takeaways_heading": "Takeaways", "focus_slugs": []})
        cfg = kb_at(os.path.join(self.tmp.name, "bare"))
        self.assertEqual(pages.skip_slugs(cfg), frozenset({"AGENTS", "log"}))

    def test_base_kit_and_no_kit_get_the_generic_values(self):
        for name, k in (("plain", ""), ("based", "base")):
            cfg = kb_at(os.path.join(self.tmp.name, name), k)
            self.assertEqual(pages.takeaways_heading(cfg), "Takeaways")
            self.assertEqual(pages.focus_slugs(cfg), frozenset())

    def test_research_kit_is_neutral(self):
        for k in ("research", "academic-research"):          # the legacy name the owner's kb.toml still uses
            cfg = kb_at(os.path.join(self.tmp.name, k), k)
            self.assertEqual(pages.takeaways_heading(cfg), "Takeaways")
            self.assertEqual(pages.focus_slugs(cfg), frozenset({"focus"}))
            self.assertEqual(pages.skip_slugs(cfg), frozenset({"AGENTS", "log", "focus"}))

    def test_a_kb_toml_pages_table_wins_over_its_kit(self):
        cfg = kb_at(os.path.join(self.tmp.name, "own"), "research",
                    '\n[pages]\ntakeaways_heading = "So what"\nfocus_slugs = ["plan"]\n')
        self.assertEqual(pages.takeaways_heading(cfg), "So what")
        self.assertEqual(pages.focus_slugs(cfg), frozenset({"plan"}))

    def test_a_bad_kb_toml_pages_table_is_refused_with_the_file_named(self):
        for i, bad in enumerate(('focus_slugs = "thesis"', 'takeaways_heading = ""', "takeaways_heading = 3")):
            cfg = kb_at(os.path.join(self.tmp.name, f"bad{i}"), "", f"\n[pages]\n{bad}\n")
            with self.assertRaises(kbconfig.KbConfigError, msg=bad) as e:
                pages.takeaways_heading(cfg)
            self.assertIn(cfg.path, str(e.exception))

    def test_every_kits_skeletons_use_the_heading_the_kit_names(self):
        """A source skeleton the kit resolves (its own, else its parent's) writes exactly the kit's heading."""
        for name in kit.names():
            cfg = kb_at(os.path.join(self.tmp.name, f"kit-{name}"), name)
            want = pages.takeaways_heading(cfg)
            seen = 0
            for path in glob.glob(str(resource("kits/base/defaults/templates")) + "/*.md"):
                resolved = paths.meta_file("templates", os.path.basename(path), root=cfg.root)
                with open(resolved, encoding="utf-8") as f:
                    found = HEADING.findall(f.read())
                for heading in found:
                    seen += 1
                    self.assertEqual(heading, want, f"kit {name}: {resolved}")
            self.assertGreater(seen, 0, f"kit {name}: no skeleton writes a takeaways section")

    def test_research_skeletons_come_from_the_research_kit_per_file(self):
        cfg = kb_at(os.path.join(self.tmp.name, "r"), "research")
        self.assertIn(os.path.join("kits", "research", "defaults", "templates", "paper.md"),
                      paths.meta_file("templates", "paper.md", root=cfg.root))
        self.assertIn(os.path.join("kits", "base", "defaults", "templates", "scope.md"),
                      paths.meta_file("templates", "scope.md", root=cfg.root))
        write(os.path.join(cfg.root, "meta", "templates", "paper.md"), "# own\n")
        self.assertEqual(paths.meta_file("templates", "paper.md", root=cfg.root),
                         os.path.join(cfg.root, "meta", "templates", "paper.md"))

    def test_no_research_kit_text_assumes_a_thesis_writer(self):
        base = str(resource("kits/research"))
        for path in glob.glob(base + "/defaults/templates/*.md") + glob.glob(base + "/prompts/*.md"):
            with open(path, encoding="utf-8") as f:
                self.assertNotRegex(f.read(), r"(?i)thesis|\bMSc\b|theoretical machine learning", path)

    def test_no_engine_skeleton_mentions_the_thesis(self):
        for path in glob.glob(str(resource("kits/base/defaults/templates")) + "/*.md"):
            with open(path, encoding="utf-8") as f:
                self.assertNotRegex(f.read(), r"(?i)thesis", path)


class KitValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"KB_KITS_DIR": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def kit(self, pages_table):
        write(os.path.join(self.tmp.name, "k", "kit.toml"), f'[kit]\nname = "k"\nversion = 1\n\n[pages]\n{pages_table}\n')

    def test_a_kit_may_hold_pages(self):
        self.kit('takeaways_heading = "Lessons"\nfocus_slugs = ["plan"]')
        self.assertEqual(kit.load("k")["pages"]["takeaways_heading"], "Lessons")

    def test_bad_pages_values_are_refused(self):
        for bad in ('takeaways_heading = ""', "takeaways_heading = 3", 'focus_slugs = "plan"', "focus_slugs = [1]"):
            self.kit(bad)
            with self.assertRaises(kit.KitError, msg=bad):
                kit.load("k")


class MigrationTests(unittest.TestCase):
    PAGE = "# P\n\n## Key equations\n\n## Takeaways for my thesis\n- a\n\n## Links out\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        write(os.path.join(self.root, "wiki", "paper-x.md"), self.PAGE)
        write(os.path.join(self.root, "wiki", "idea-y.md"), "# Y\n\nTakeaways for my thesis in prose stays.\n")
        write(os.path.join(self.root, "think", "n.md"), self.PAGE)

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def test_dry_run_plans_and_writes_nothing(self):
        self.assertEqual(migration.plan(self.root, "Takeaways"), [os.path.join("wiki", "paper-x.md")])
        self.assertEqual(self.read("wiki/paper-x.md"), self.PAGE)

    def test_apply_renames_only_the_heading_line_and_is_idempotent(self):
        self.assertEqual(migration.apply(self.root, "Takeaways"), [os.path.join("wiki", "paper-x.md")])
        self.assertEqual(self.read("wiki/paper-x.md"), self.PAGE.replace("## Takeaways for my thesis", "## Takeaways"))
        self.assertIn("Takeaways for my thesis in prose", self.read("wiki/idea-y.md"))
        self.assertEqual(self.read("think/n.md"), self.PAGE)
        self.assertEqual(migration.apply(self.root, "Takeaways"), [])

    def test_a_research_kb_has_nothing_to_do(self):
        self.assertEqual(migration.plan(self.root, "Takeaways for my thesis"), [])

    def test_a_kb_overriding_the_heading_keeps_its_pages_through_migrate_and_lint(self):
        """The owner's thesis kb sets the old heading and focus page in its own kb.toml: the neutral research-kit
        default must neither rewrite its pages nor make its focus page look like an orphan."""
        from unittest.mock import patch
        from kb_distillery.vault import health
        root = os.path.join(self.root, "kbs", "mine")
        cfg = kb_at(root, "research", '\n[pages]\ntakeaways_heading = "Takeaways for my thesis"\nfocus_slugs = ["thesis"]\n')
        write(os.path.join(root, "wiki", "paper-x.md"), self.PAGE)
        write(os.path.join(root, "wiki", "thesis.md"), "# Thesis\n")
        self.assertEqual(pages.takeaways_heading(cfg), "Takeaways for my thesis")
        self.assertEqual(migration.plan(root, pages.takeaways_heading(cfg)), [])
        with patch.object(kbconfig, "current", return_value=cfg):
            self.assertEqual(migration.main(["--apply"]), 0)
            self.assertFalse(health.is_orphan_slug("thesis"))
            self.assertTrue(health.is_orphan_slug("focus"))
        with open(os.path.join(root, "wiki", "paper-x.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), self.PAGE)

    def test_crlf_pages_keep_their_line_ends(self):
        write(os.path.join(self.root, "wiki", "paper-x.md"), self.PAGE.replace("\n", "\r\n"))
        with open(os.path.join(self.root, "wiki", "paper-x.md"), "w", encoding="utf-8", newline="") as f:
            f.write(self.PAGE.replace("\n", "\r\n"))
        migration.apply(self.root, "Takeaways")
        with open(os.path.join(self.root, "wiki", "paper-x.md"), encoding="utf-8", newline="") as f:
            self.assertIn("## Takeaways\r\n", f.read())


if __name__ == "__main__":
    unittest.main()
