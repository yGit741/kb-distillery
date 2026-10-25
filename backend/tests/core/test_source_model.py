#!/usr/bin/env python3
"""The source model (schema 1.0): the spec map is total, the 0008 migration rewrites only front
matter and dispositions (idempotent, refuses open sessions, backs up), lint enforces layer/type and
names the replacement for every retired name, and a paradigm merge moves kb-0.13.z to kb-1.0.0."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

from kb.paths import CODE_DIR, vault_root
META = os.path.join(vault_root(), "meta")
from kb.git import commit_policy as cp
from kb.core import schema
from kb.ops import invariants as inv
from tests.git.test_commit_policy import TempRepo, git, kb_msg

SPEC_PATH = os.path.join(META, "migration", "source-model", "spec_map.json")
MIGRATION = os.path.join(CODE_DIR, "migrations", "0008_source_model.py")
# Every type and disposition schema 0.13 knew (backend/src/kb/core/schema.py at kb-0.13.1).
OLD_TYPES = {"paper", "part", "lecture", "article", "video", "conversation", "ai-chat", "blog-post",
             "book", "notebook", "course", "series", "theme", "concept", "person", "question",
             "distilled-think", "scope"}
OLD_DISPOSITIONS = {"queued", "digested", "partial", "skip", "sidecar"}
OLD_DEPTHS = {"catalog", "easy", "full", "deep"}
# Types renamed after 1.0 (the spec map is the frozen 1.0 artifact): 0010_mail_type.
RENAMED_SINCE = {"conversation": "mail"}


def load_migration():
    spec = importlib.util.spec_from_file_location("m0008", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SpecMapTotality(unittest.TestCase):
    def setUp(self):
        with open(SPEC_PATH, encoding="utf-8") as f:
            self.spec = json.load(f)

    def test_every_old_and_new_type_is_mapped_to_its_schema_layer(self):
        self.assertTrue(OLD_TYPES <= set(self.spec["types"]))
        self.assertTrue(set(schema.TYPE_STATUS) <= {RENAMED_SINCE.get(t, t) for t in self.spec["types"]})
        for old, m in self.spec["types"].items():
            now = RENAMED_SINCE.get(m["type"], m["type"])
            self.assertIn(now, schema.TYPE_STATUS, old)
            self.assertEqual(m["layer"], schema.LAYER_OF[now], old)
        self.assertEqual(self.spec["types"]["theme"]["type"], "topic")
        self.assertEqual(self.spec["types"]["concept"]["type"], "idea")

    def test_depth_and_dispositions_are_total(self):
        self.assertEqual(self.spec["rename_fields"], {"digestion-status": "depth"})
        self.assertEqual(set(self.spec["values"]["depth"]), OLD_DEPTHS)
        self.assertTrue(set(self.spec["values"]["depth"].values()) <= set(schema.DEPTH))
        self.assertEqual(self.spec["values"]["depth"]["catalog"], "listed")
        self.assertTrue(OLD_DISPOSITIONS <= set(self.spec["dispositions"]))
        self.assertTrue(set(self.spec["dispositions"].values()) <= schema.DISPOSITIONS)
        self.assertEqual(self.spec["dispositions"]["digested"], "source")

    def test_prefixes_unchanged(self):
        self.assertEqual(self.spec["prefixes"]["topic"], "theme-")
        self.assertEqual(self.spec["prefixes"]["idea"], "")
        for t, p in self.spec["prefixes"].items():
            if t in RENAMED_SINCE:
                continue
            self.assertEqual(schema.SLUG_PREFIX.get(t, ""), p, t)

    def test_layers_partition_the_types(self):
        layers = {}
        for t, l in schema.LAYER_OF.items():
            layers.setdefault(l, set()).add(t)
        self.assertEqual(set(layers), set(schema.LAYERS))
        self.assertEqual(schema.SOURCE_TYPES, layers["source"])
        self.assertEqual(schema.COLLECTION_TYPES | {"scope"}, layers["collection"])
        self.assertEqual(schema.CONCEPT_TYPES | {"distilled-think"}, layers["concept"])

    def test_migration_produces_the_schema(self):
        self.assertEqual(tuple(load_migration().PRODUCES), (1, 0))       # the paradigm this migration produced
        self.assertEqual(tuple(self.spec["schema"]), (1, 0))
        self.assertGreaterEqual(schema.SCHEMA_VERSION, (1, 0))


IDEA = "---\ntype: concept\nstatus: seed\n---\n\n# I\n\ntype: concept stays in the body\n\n## My notes\n\nmine\n"
PAPER = ("---\ntype: paper\nstatus: to-read\ndigestion-status: catalog   # a comment\nraw: [raw/a.pdf, raw/b.pdf]\n---\n"
         "\n# P\n\ndigestion-status: catalog in the body\n")
TOPIC = "---\ntype: theme\nstatus: seed\n---\n\n# T\n"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kb-0008-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "wiki"))
        os.makedirs(os.path.join(self.root, "meta", "migration", "source-model"))
        shutil.copy(SPEC_PATH, os.path.join(self.root, "meta", "migration", "source-model"))
        self.w("wiki/tensor-rank.md", IDEA)
        self.w("wiki/paper-p.md", PAPER)
        self.w("wiki/theme-learning-theory.md", TOPIC)
        self.w("meta/corpus.tsv", "# header\npath\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n"
               "raw/a.pdf\tabc\tprinted-docs\tdigested\tpaper-p\t\t\n"
               "raw/c.png\tdef\timages\tasset:raw/x.md\t\t\t\n"
               "raw/d.pdf\t123\tprinted-docs\tqueued\t\t\t\n")
        self.mod = load_migration()

    def w(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def r(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def test_apply_rewrites_front_matter_only_and_is_idempotent(self):
        before = inv.snapshot(self.root, lint=False)
        self.mod.apply(self.root, dry_run=True)
        self.assertEqual(self.r("wiki/tensor-rank.md"), IDEA)                    # dry run writes nothing
        self.assertIn("+type: idea", self.r("meta/.migrate/source-model/plan.diff"))
        self.mod.apply(self.root)
        self.assertEqual(self.r("wiki/tensor-rank.md"), IDEA.replace("type: concept\n", "type: idea\nlayer: concept\n", 1))
        self.assertEqual(self.r("wiki/paper-p.md"), PAPER.replace("type: paper\n", "type: paper\nlayer: source\n", 1)
                         .replace("digestion-status: catalog   #", "depth: listed   #", 1))
        self.assertTrue(self.r("wiki/theme-learning-theory.md").startswith("---\ntype: topic\nlayer: concept\n"))
        self.assertIn("raw/a.pdf\tabc\tprinted-docs\tsource\tpaper-p", self.r("meta/corpus.tsv"))
        self.assertIn("asset:raw/x.md", self.r("meta/corpus.tsv"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "meta/.migrate/source-model/backup/wiki/paper-p.md")))
        after = inv.snapshot(self.root, lint=False)
        with open(SPEC_PATH, encoding="utf-8") as f:
            spec = json.load(f)
        self.assertEqual(inv.compare(before, after, spec, out=lambda *_: None), [])
        texts = {p: self.r(f"wiki/{p}.md") for p in ("tensor-rank", "paper-p", "theme-learning-theory")}
        corpus = self.r("meta/corpus.tsv")
        self.mod.apply(self.root)                                                # second run: no change
        self.assertEqual({p: self.r(f"wiki/{p}.md") for p in texts}, texts)
        self.assertEqual(self.r("meta/corpus.tsv"), corpus)

    def test_refuses_open_session(self):
        os.makedirs(os.path.join(self.root, "meta", ".ingest", "abc"))
        self.w("meta/.ingest/abc/session.json", json.dumps({"status": "open", "raw": "raw/a.pdf"}))
        with self.assertRaises(RuntimeError):
            self.mod.apply(self.root)
        self.assertEqual(self.r("wiki/tensor-rank.md"), IDEA)
        self.w("meta/.ingest/abc/session.json", json.dumps({"status": "closed", "digestion_status": "full"}))
        self.mod.apply(self.root)                                     # closed sessions are history
        self.assertIn("digestion_status", self.r("meta/.ingest/abc/session.json"))


class LintRetiredNames(unittest.TestCase):
    def setUp(self):
        from kb.lint import lint
        self.lint = lint
        self.old = lint.ROOT
        self.root = tempfile.mkdtemp(prefix="kb-lint-sm-")
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "wiki"))
        lint.ROOT = self.root
        self.addCleanup(setattr, lint, "ROOT", self.old)

    def errors(self, slug, text):
        with open(os.path.join(self.root, "wiki", f"{slug}.md"), "w", encoding="utf-8") as f:
            f.write(text)
        self.lint.errors.clear()
        self.lint.warnings.clear()
        self.lint.check_wiki()
        return [e for e in self.lint.errors if f"{slug}.md" in e]

    def test_retired_type_names_its_replacement(self):
        errs = self.errors("tensor-rank", "---\ntype: concept\nstatus: seed\n---\n# T\n")
        self.assertTrue(any("retired" in e and "type: idea" in e for e in errs), errs)

    def test_missing_or_wrong_layer(self):
        self.assertTrue(any("missing `layer:`" in e for e in self.errors("x", "---\ntype: idea\nstatus: seed\n---\n# X\n")))
        self.assertTrue(any("disagrees" in e for e in self.errors("y", "---\ntype: idea\nlayer: source\nstatus: seed\n---\n# Y\n")))
        self.assertEqual(self.errors("z", "---\ntype: idea\nlayer: concept\nstatus: seed\n---\n# Z\n"), [])

    def test_retired_depth_key_and_value(self):
        base = "---\ntype: video\nlayer: source\nstatus: to-read\nraw: none\nurl: https://x.org\n"
        errs = self.errors("video-a", base + "digestion-status: catalog\n---\n# A\n")
        self.assertTrue(any("`digestion-status:` is retired" in e for e in errs), errs)
        errs = self.errors("video-b", base + "depth: catalog\n---\n# B\n")
        self.assertTrue(any("depth: listed" in e for e in errs), errs)
        self.assertEqual(self.errors("video-c", base + "depth: listed\n---\n# C\n"), [])

    def test_retired_disposition(self):
        os.makedirs(os.path.join(self.root, "meta"))
        os.makedirs(os.path.join(self.root, "raw", "printed-docs"))
        with open(os.path.join(self.root, "raw", "printed-docs", "a.md"), "w") as f:
            f.write("x")
        sha = self.lint.sha1("raw/printed-docs/a.md")
        with open(os.path.join(self.root, "meta", "corpus.tsv"), "w") as f:
            f.write(f"path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\nraw/printed-docs/a.md\t{sha}\tprinted-docs\tdigested\t\t\t\n")
        self.lint.errors.clear()
        self.lint.reconcile(["raw/printed-docs/a.md"], set(), {"raw/printed-docs/a.md"})
        self.assertTrue(any("retired" in e and "'source'" in e for e in self.lint.errors), self.lint.errors)


class MajorVersionBump(unittest.TestCase):
    """The user asked for +1 in the first digit: a paradigm PR, kb-0.13.z → kb-1.0.0 → kb-1.0.1."""

    def setUp(self):
        self.repo = TempRepo()
        self.repo.commit("chore: init (retro)", "README.md")
        self.addCleanup(self.repo.close)

    def test_merge_version_from_013(self):
        self.assertEqual(cp.merge_version((1, 0), (0, 13, 1), "paradigm"), (1, 0, 0))
        with self.assertRaises(ValueError):                    # a schema (y+1) PR may not do this
            cp.merge_version((1, 0), (0, 13, 1), "schema")
        with self.assertRaises(ValueError):
            cp.merge_version((0, 14), (0, 13, 1), "paradigm")

    def test_next_version_after_major(self):
        self.repo.commit(kb_msg("refine", "a", "0.13.1"), "wiki/a.md")
        self.assertEqual(cp.next_version(self.repo.path, schema_version=(1, 0)), (1, 0, 1))

    def test_push_range_accepts_paradigm_merge(self):
        old = self.repo.commit(kb_msg("refine", "a", "0.13.1"), "wiki/a.md")
        git(self.repo.path, "checkout", "-q", "-b", "infra/source-model")
        self.repo.commit("paradigm(schema): source model", "backend/src/kb/core/schema.py")
        git(self.repo.path, "checkout", "-q", "main")
        git(self.repo.path, "merge", "-q", "--no-ff", "-m",
            "paradigm(schema): source model (#62)\n\nKB-Version: 1.0.0", "infra/source-model")
        self.repo.commit(kb_msg("digest", "b", "1.0.1"), "wiki/b.md")
        self.assertEqual(cp.check_push_range(self.repo.path, old, self.repo.head()), [])
        self.assertEqual(cp.last_version(self.repo.path), (1, 0, 1))

    def test_push_range_rejects_minor_bump_on_paradigm(self):
        old = self.repo.commit(kb_msg("refine", "a", "0.13.1"), "wiki/a.md")
        git(self.repo.path, "checkout", "-q", "-b", "infra/x")
        self.repo.commit("paradigm(schema): x", "backend/src/kb/core/schema.py")
        git(self.repo.path, "checkout", "-q", "main")
        git(self.repo.path, "merge", "-q", "--no-ff", "-m", "paradigm(schema): x (#9)\n\nKB-Version: 0.14.0", "infra/x")
        self.assertTrue(any("1.0.0" in v for v in cp.check_push_range(self.repo.path, old, self.repo.head())))

    def test_share_build_reads_the_schema_major(self):
        from kb.share import build as sb
        self.assertEqual(sb.schema_major(META.rsplit("/", 1)[0], "kb-0.9.6"), 0)

    def test_ship_pr_body_says_major(self):
        from kb.git import ship
        self.assertEqual(ship._schema_kind(["chore(x): a", "paradigm(schema): b"]), "paradigm")
        self.assertIn("x+1", ship.pr_body(["paradigm(schema): b"]))
        body = ship.pr_body(["paradigm(schema): b"], "invariants hold")
        self.assertTrue(body.rstrip().endswith("## Notes\n\ninvariants hold"))
        self.assertNotIn("## Notes", ship.pr_body(["feat(x): y"], "  "))


if __name__ == "__main__":
    unittest.main()
