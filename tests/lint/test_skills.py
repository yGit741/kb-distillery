#!/usr/bin/env python3
"""Tests for src/kb_distillery/lint/lint_skills.py."""
import os
import shutil
import sys
import tempfile
import unittest
from typing import Optional

from kb_distillery.config.kb import checkout_root
CHECKOUT_ROOT = checkout_root()
ROOT = CHECKOUT_ROOT          # skills are code

from kb_distillery.lint.lint_skills import run_checks


def _minimal_skill(name: str, description: Optional[str] = None, audience: str = "dev", mode: str = "write",
                   extra: str = "") -> str:
    desc = description or (
        f"Test skill {name}. Use for testing only. Do NOT use in production."
    )
    return f"""---
name: {name}
description: {desc}
audience: {audience}
mode: {mode}
---

# {name}

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `{name}`

## Do NOT

- Never use outside tests

## CLI

```bash
python3 -m kb_distillery.lint.lint
```
{extra}"""


def _minimal_readme(skill_name: str, meta: bool = False) -> str:
    ladder = ""
    if not meta:
        ladder = f"""
## Token budgets

| Skill | LLM tier | Budget (in) | Runs without asking |
|-------|----------|-------------|---------------------|
| `{skill_name}` | none | 0 | yes |
"""
    return f"""# Skill ladder

{ladder}
## Skills

| Skill | Purpose |
|-------|---------|
| [{skill_name}]({skill_name}/SKILL.md) | test skill |
"""


class LintSkillsFixtureTests(unittest.TestCase):
    def _make_tree(self, skill_name: str = "test-skill", meta: bool = False) -> str:
        tmp = tempfile.mkdtemp()
        skills = os.path.join(tmp, "skills")
        os.makedirs(os.path.join(skills, skill_name))
        with open(os.path.join(skills, skill_name, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(_minimal_skill(skill_name))
        with open(os.path.join(skills, "README.md"), "w", encoding="utf-8") as f:
            f.write(_minimal_readme(skill_name, meta=meta))
        return tmp

    def tearDown(self):
        pass

    def test_existing_skills_pass(self):
        n_err, _ = run_checks()
        self.assertEqual(n_err, 0, "existing skills (every kit and .claude/skills) should pass lint-skills")

    def test_missing_skill_md_fails(self):
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        os.remove(os.path.join(skills, "test-skill", "SKILL.md"))
        n_err, _ = run_checks(skills_roots=[skills])
        self.assertGreater(n_err, 0)
        shutil.rmtree(tmp)

    def test_name_mismatch_fails(self):
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        path = os.path.join(skills, "test-skill", "SKILL.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_minimal_skill("wrong-name"))
        n_err, _ = run_checks(skills_roots=[skills])
        self.assertGreater(n_err, 0)
        shutil.rmtree(tmp)

    def test_fake_cli_fails(self):
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        path = os.path.join(skills, "test-skill", "SKILL.md")
        body = _minimal_skill("test-skill").replace(
            "python3 -m kb_distillery.lint.lint",
            "python3 -m kb_distillery.ingest not-a-command",
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        n_err, _ = run_checks(skills_roots=[skills])
        self.assertGreater(n_err, 0)
        shutil.rmtree(tmp)

    def test_readme_ghost_skill_fails(self):
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        readme = os.path.join(skills, "README.md")
        with open(readme, "w", encoding="utf-8") as f:
            f.write(_minimal_readme("ghost-skill"))
        n_err, _ = run_checks(skills_roots=[skills])
        self.assertGreater(n_err, 0)
        shutil.rmtree(tmp)

    def test_strict_warn_promotion(self):
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        path = os.path.join(skills, "test-skill", "SKILL.md")
        # Remove Triggers section to trigger W1
        body = _minimal_skill("test-skill").replace("## Triggers\n\n- `test-skill`\n\n", "")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        n_err_loose, n_warn = run_checks(skills_roots=[skills], strict=False)
        self.assertEqual(n_err_loose, 0)
        self.assertGreater(n_warn, 0)
        n_err_strict, _ = run_checks(skills_roots=[skills], strict=True)
        self.assertGreater(n_err_strict, 0)
        shutil.rmtree(tmp)

    def _warnings_for(self, description: str):
        from kb_distillery.lint import lint_skills
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        path = os.path.join(skills, "test-skill", "SKILL.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_minimal_skill("test-skill", description))
        n_err, _ = run_checks(skills_roots=[skills])
        warns = list(lint_skills.warnings)
        shutil.rmtree(tmp)
        return n_err, warns

    def _errors_for(self, **kw):
        from kb_distillery.lint import lint_skills
        tmp = self._make_tree()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "skills", "test-skill", "SKILL.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_minimal_skill("test-skill", **kw))
        run_checks(skills_roots=[os.path.join(tmp, "skills")])
        return list(lint_skills.errors)

    def test_audience_and_mode_are_required(self):
        for field in ("audience", "mode"):
            tmp = self._make_tree()
            self.addCleanup(shutil.rmtree, tmp)
            path = os.path.join(tmp, "skills", "test-skill", "SKILL.md")
            with open(path, encoding="utf-8") as f:
                body = "".join(l for l in f if not l.startswith(field + ":"))
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            n_err, _ = run_checks(skills_roots=[os.path.join(tmp, "skills")])
            self.assertEqual(n_err, 1, field)

    def test_audience_and_mode_values_are_checked(self):
        self.assertTrue(any("audience must be" in e for e in self._errors_for(audience="everyone")))
        self.assertTrue(any("mode must be" in e for e in self._errors_for(mode="rw")))

    def test_app_skill_must_not_mention_ship_or_prs(self):
        from kb_distillery.lint import lint_skills
        app = lint_skills.check_skill_md  # an app skill only lives in a kit root; check the body rule directly
        tmp = self._make_tree()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "skills", "test-skill", "SKILL.md")
        for words, bad in (("Open a PR when done.", True), ("Then run ship merge.", True), ("A relationship map.", False)):
            with open(path, "w", encoding="utf-8") as f:
                f.write(_minimal_skill("test-skill", audience="app", extra=words + "\n"))
            lint_skills.errors.clear()
            app(os.path.relpath(path, lint_skills.ROOT).replace(os.sep, "/"), is_top_level=True, kit=True)
            hit = any("must not mention ship" in e for e in lint_skills.errors)
            self.assertEqual(hit, bad, words)

    def test_read_skill_must_not_name_write_tools(self):
        self.assertTrue(any("Write / Edit" in e for e in self._errors_for(mode="read", extra="Use the Edit tool on the page.\n")))
        self.assertFalse(any("Write / Edit" in e for e in self._errors_for(mode="write", extra="Use the Edit tool on the page.\n")))
        self.assertFalse(any("Write / Edit" in e for e in self._errors_for(mode="read", extra="Read the page.\n")))

    def test_kit_skills_must_be_app_and_engine_skills_dev(self):
        from kb_distillery.lint import lint_skills
        self.assertTrue(any("must have audience: dev" in e for e in self._errors_for(audience="app")))
        self.assertEqual(self._errors_for(audience="dev"), [])
        self.assertTrue(lint_skills.AUDIENCES == {"app", "dev"})

    def test_description_without_use_trigger_warns(self):
        n_err, warns = self._warnings_for("Does a thing for the vault. Do NOT use for anything else.")
        self.assertEqual(n_err, 0)
        self.assertTrue(any('"Use for/when' in w for w in warns), warns)

    def test_description_without_do_not_clause_warns(self):
        n_err, warns = self._warnings_for("Does a thing for the vault. Use for thing, do-thing. Never auto-run.")
        self.assertEqual(n_err, 0)
        self.assertTrue(any('"Do NOT use for' in w for w in warns), warns)

    def test_good_description_has_no_trigger_warnings(self):
        _, warns = self._warnings_for("Does a thing. Use for thing, do-thing. Do NOT use for other things.")
        self.assertFalse(any("trigger line" in w or "near-miss" in w for w in warns), warns)


class SkillRootsTests(unittest.TestCase):
    def test_roots_are_each_kit_and_the_engine_skills(self):
        from kb_distillery.lint import lint_skills
        rel = {os.path.relpath(r, ROOT).replace(os.sep, "/") for r in lint_skills.SKILLS_ROOTS}
        want = {"src/kb_distillery/kits/base/skills", "src/kb_distillery/kits/research/skills"}
        if os.path.isdir(os.path.join(ROOT, ".claude", "skills")):      # owner-only: export-ignored from the public repo
            want.add(".claude/skills")
        self.assertTrue(want <= rel, rel)
        self.assertEqual(".claude/skills" in rel, os.path.isdir(os.path.join(ROOT, ".claude", "skills")))

    @unittest.skipUnless(os.path.isdir(os.path.join(ROOT, ".claude", "skills")), "owner tooling: .claude/ is export-ignored, so the public checkout has none")
    def test_engine_skills_are_real_files_not_a_symlink(self):
        path = os.path.join(ROOT, ".claude", "skills")
        self.assertTrue(os.path.isdir(path) and not os.path.islink(path), f"{path} must be a real folder")
        self.assertFalse(os.path.exists(os.path.join(ROOT, "skills")), "the top-level skills folder moved into the kits")

    def _two_roots(self, second_skill: str):
        a, b = self._make_root("one-skill"), self._make_root(second_skill)
        return a, b

    def _make_root(self, skill_name: str) -> str:
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        skills = os.path.join(tmp, "skills")
        os.makedirs(os.path.join(skills, skill_name))
        with open(os.path.join(skills, skill_name, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(_minimal_skill(skill_name))
        with open(os.path.join(skills, "README.md"), "w", encoding="utf-8") as f:
            f.write(_minimal_readme(skill_name))
        return skills

    def test_two_folders_each_lint_against_their_own_readme(self):
        a, b = self._two_roots("two-skill")
        n_err, _ = run_checks(skills_roots=[a, b])
        self.assertEqual(n_err, 0)
        with open(os.path.join(b, "README.md"), "w", encoding="utf-8") as f:
            f.write(_minimal_readme("one-skill"))         # b's README lists a skill that is only in a
        n_err, _ = run_checks(skills_roots=[a, b])
        self.assertGreater(n_err, 0)

    def test_a_skill_name_in_two_folders_fails(self):
        a, b = self._two_roots("one-skill")
        n_err, _ = run_checks(skills_roots=[a, b])
        self.assertGreater(n_err, 0)

    def test_distill_lines_are_checked(self):
        from kb_distillery.lint import lint_skills
        for line, ok in (("distill lint", True), ("distill ingest catalog raw/inbox/x.pdf", True), ("distill ops status", True),
                         ("distill digest easy x", True), ("distill ingest not-a-command", False), ("distill nonsense", False),
                         ("distill digest bogus", False)):
            lint_skills.errors.clear()
            lint_skills.validate_cli_line("x/SKILL.md", line)
            self.assertEqual(not lint_skills.errors, ok, line)

    def test_a_kit_skill_may_not_use_pixi(self):
        from kb_distillery.lint import lint_skills
        lint_skills.errors.clear()
        lint_skills.validate_cli_line("x/SKILL.md", "pixi run lint", kit=True)
        self.assertTrue(lint_skills.errors)
        lint_skills.errors.clear()
        lint_skills.validate_cli_line("x/SKILL.md", "pixi run lint", kit=False)
        self.assertFalse(lint_skills.errors)


if __name__ == "__main__":
    unittest.main()
