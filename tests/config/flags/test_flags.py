"""Feature-flag registry (meta/flags.toml): validation, values, codegen --check."""
import json
import shutil
import tempfile
import tomllib
import textwrap
import unittest
from pathlib import Path

from kb_distillery.config.flags import codegen
from kb_distillery.config.flags.registry import FLAGS_TOML, FlagError, load, parse
from kb_distillery.config.paths import ROOT

GOOD = dict(name="screen.x", description="d", owner="me", kind="build", default=False,
            envs={"local": True, "private": True, "public": False})


def flag(**kw):
    import datetime as dt
    return {**GOOD, "created": dt.date(2026, 1, 1), "expires": dt.date(2027, 1, 1), **kw}


class RegistryTests(unittest.TestCase):
    def test_real_registry_loads(self):
        reg = load()
        self.assertIn("screen.share", reg.names())
        self.assertTrue(reg.value("screen.share", "private"))
        self.assertFalse(reg.value("screen.share", "public"))
        self.assertFalse(reg.value("screen.share", "local"))

    def test_unknown_env_uses_default(self):
        self.assertFalse(parse({"flag": [flag()]}).value("screen.x", "staging"))

    def test_unknown_flag(self):
        with self.assertRaisesRegex(KeyError, "unknown flag"):
            parse({"flag": [flag()]}).value("nope", "local")

    def assertInvalid(self, data, *needles):
        with self.assertRaises(FlagError) as cm:
            parse(data)
        for n in needles:
            self.assertIn(n, str(cm.exception))

    def test_missing_env(self):
        self.assertInvalid({"flag": [flag(envs={"local": True, "private": True})]}, "flag screen.x", "envs.public", "Field required")

    def test_bad_date(self):
        self.assertInvalid({"flag": [flag(created="2026-13-01")]}, "flag screen.x: created")

    def test_expires_before_created(self):
        import datetime as dt
        self.assertInvalid({"flag": [flag(expires=dt.date(2025, 1, 1))]}, "must be after created")

    def test_bad_kind_name_extra_and_duplicate(self):
        self.assertInvalid({"flag": [flag(kind="nightly")]}, "kind")
        self.assertInvalid({"flag": [flag(name="Bad Name")]}, "dotted lower-case")
        self.assertInvalid({"flag": [flag(extra=1)]}, "extra")
        self.assertInvalid({"flag": [flag(), flag()]}, "duplicate name")
        self.assertInvalid({"flags": []}, "unknown top-level")

    def test_env_values_must_be_bool(self):
        self.assertInvalid({"flag": [flag(envs={"local": "yes", "private": True, "public": False})]}, "envs.local")

    def test_toml_errors_are_flag_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "flags.toml"
            p.write_text("[[flag]\n", encoding="utf-8")
            with self.assertRaisesRegex(FlagError, "TOML syntax"):
                load(p)
            with self.assertRaisesRegex(FlagError, "not found"):
                load(Path(d) / "missing.toml")


class CodegenTests(unittest.TestCase):
    def test_repo_is_up_to_date(self):
        self.assertEqual(codegen.main(["--check"]), 0)

    def test_check_detects_stale_and_write_fixes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "meta").mkdir()
            shutil.copy(FLAGS_TOML, root / "meta" / "flags.toml")
            self.assertEqual(codegen.main(["--check"], root=root), 2)  # no feature folders yet
            for s in ("home", "graph", "pages", "lifecycle", "share", "start"):
                (root / f"web/src/features/{s}").mkdir(parents=True)
                (root / f"web/src/features/{s}/index.tsx").write_text("")
            self.assertEqual(codegen.main(["--check"], root=root), 1)  # nothing generated yet
            self.assertEqual(codegen.main([], root=root), 0)
            self.assertEqual(codegen.main(["--check"], root=root), 0)
            gen = (root / codegen.GEN_TS).read_text(encoding="utf-8")
            toml_names = sorted(f["name"] for f in tomllib.loads((root / "meta" / "flags.toml").read_text())["flag"])   # read independently of load()
            union = " | ".join(json.dumps(n) for n in toml_names)
            self.assertIn(f"export type FlagName = "agent-mode" | "calm-graph" | "chat-full" | "graph-intent" | "graph-relations" | "graph-shell" | "header-fold" | "inbox-pickup" | "kb-view" | "legend-counts" | "line-routing" | "parsed-pdf" | "pin-fan" | "research-tools" | "screen.digest-jobs" | "screen.first-run" | "screen.lifecycle" | "screen.share" | "screen.start" | "screen.think" | "semantic-search" | "show-thinking" | "spark-chat" | "ui.system-flags-tab" | "views-panel";", gen)
            pub = (root / codegen.modules_path("public")).read_text(encoding="utf-8")
            priv = (root / codegen.modules_path("private")).read_text(encoding="utf-8")
            self.assertNotIn("lifecycle", pub)
            self.assertIn("features/share/index.tsx", priv)
            (root / "meta" / "flags.toml").write_text(
                (root / "meta" / "flags.toml").read_text().replace("public = false }", "public = true }", 1))
            self.assertEqual(codegen.main(["--check"], root=root), 1)

    def test_invalid_registry_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.toml"
            p.write_text(textwrap.dedent('[[flag]]\nname = "x"\n'), encoding="utf-8")
            self.assertEqual(codegen.main(["--check", "--flags", str(p)], root=Path(ROOT)), 2)


if __name__ == "__main__":
    unittest.main()
