#!/usr/bin/env python3
"""Tests for backend/src/kb/lint/lint_skills.py."""
import os
import shutil
import sys
import tempfile
import unittest
from typing import Optional

from kb.paths import vault_root
ROOT = vault_root()

from kb.lint.lint_skills import run_checks


def _minimal_skill(name: str, description: Optional[str] = None) -> str:
    desc = description or (
        f"Test skill {name}. Use for testing only. Do NOT use in production."
    )
    return f"""---
name: {name}
description: {desc}
---

# {name}

**LLM tier:** none · **Budget:** 0 tokens

## Triggers

- `{name}`

## Do NOT

- Never use outside tests

## CLI

```bash
python3 -m kb.lint.lint
```
"""


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
        n_err, _ = run_checks(skills_root=os.path.join(ROOT, "skills"))
        self.assertEqual(n_err, 0, "existing skills should pass lint-skills")

    def test_missing_skill_md_fails(self):
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        os.remove(os.path.join(skills, "test-skill", "SKILL.md"))
        n_err, _ = run_checks(skills_root=skills)
        self.assertGreater(n_err, 0)
        shutil.rmtree(tmp)

    def test_name_mismatch_fails(self):
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        path = os.path.join(skills, "test-skill", "SKILL.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(_minimal_skill("wrong-name"))
        n_err, _ = run_checks(skills_root=skills)
        self.assertGreater(n_err, 0)
        shutil.rmtree(tmp)

    def test_fake_cli_fails(self):
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        path = os.path.join(skills, "test-skill", "SKILL.md")
        body = _minimal_skill("test-skill").replace(
            "python3 -m kb.lint.lint",
            "python3 -m kb.ingest not-a-command",
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        n_err, _ = run_checks(skills_root=skills)
        self.assertGreater(n_err, 0)
        shutil.rmtree(tmp)

    def test_readme_ghost_skill_fails(self):
        tmp = self._make_tree()
        skills = os.path.join(tmp, "skills")
        readme = os.path.join(skills, "README.md")
        with open(readme, "w", encoding="utf-8") as f:
            f.write(_minimal_readme("ghost-skill"))
        n_err, _ = run_checks(skills_root=skills)
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
        n_err_loose, n_warn = run_checks(skills_root=skills, strict=False)
        self.assertEqual(n_err_loose, 0)
        self.assertGreater(n_warn, 0)
        n_err_strict, _ = run_checks(skills_root=skills, strict=True)
        self.assertGreater(n_err_strict, 0)
        shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
