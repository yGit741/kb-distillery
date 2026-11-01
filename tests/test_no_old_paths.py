"""The retired layout (backend/, frontend/, tools/, kbs/demo, package `kb`) stays gone, and so do the Lane D moves:
`maintenance/{daily_sync,notify,export,fix_math,rename_raw}`, the top-level `report/` package, the per-user folder
`~/.config/thesis-kb` (now `~/.config/kb-distillery`, `config/userdir.py`) and the keychain service `thesis-kb-gmail`,
and the Lane C moves: `templates/` (now `src/kb_distillery/kits/<kit>/kit.toml`, read by `vault/kit.py`) and
`meta-defaults/` (now `src/kb_distillery/kits/base/defaults/`), the root `skills/` folder with its `.claude/skills`
symlink, `pixi run sync-skills` and `SKILL_TEMPLATE.md` (now `src/kb_distillery/kits/<kit>/skills/`, real files in
`.claude/skills/`, `docs/guides/write-a-skill.md` and `kits/base/skills/_TEMPLATE.md`).

There are no import shims: a star-import shim breaks mock.patch, `python -m` and -W error filters. Instead this scan
fails on any tracked file that still names the old module or path strings. Inputs come from `git ls-files` only (the
user's knowledge bases and worktrees are on disk but untracked)."""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RETIRED = {
    "import of package kb": re.compile(r"(?<![\w.-])from kb(?:\.(?!toml\b)|\s+import\b)|(?m:^[ \t]*import kb(?:\.\w+)*(?:\s+as\s+\w+)?[ \t]*$)"),
    "mock.patch of kb.": re.compile(r"""patch(?:\.object|\.dict)?\(\s*["']kb\."""),
    "python -m kb.": re.compile(r"python3? -m kb(?:\.|\s|$)"),
    "backend/src or backend/tests": re.compile(r"backend/(?:src|tests)"),
    "frontend/": re.compile(r"(?<![\w-])frontend/"),
    "tools/": re.compile(r"(?<![\w-])tools/"),
    "kbs/demo": re.compile(r"kbs/demo"),
    "maintenance/ module that moved or was deleted": re.compile(
        r"kb_distillery[./]maintenance[./](?:daily_sync|notify|export|fix_math|rename_raw)\b"
        r"|from kb_distillery\.maintenance import (?:daily_sync|notify|export|fix_math|rename_raw)\b"
        r"|maintenance/(?:daily_sync|notify|export|fix_math|rename_raw)\.py"),
    "top-level report package": re.compile(r"kb_distillery\.report\b|src/kb_distillery/report/"),
    "~/.config/thesis-kb": re.compile(r"\.config/thesis-kb"),
    "keychain service thesis-kb-gmail": re.compile(r"thesis-kb-gmail"),
    "meta-defaults/": re.compile(r"meta-defaults|META_DEFAULTS_DIR"),
    "root skills/ folder, sync-skills or SKILL_TEMPLATE": re.compile(
        r"(?<![\w./~-])skills/|sync[-_]skills|SKILL_TEMPLATE|(?<![\w])\.\./skills\b"),
    "templates/ kit folder, template.toml, core.template or $KB_TEMPLATES_DIR": re.compile(
        r"(?<![\w./-])templates/(?:starter|academic-research|<name>)|template\.toml|KB_TEMPLATES_DIR"
        r"|kb_distillery[./]core[./]template\b|core import template\b|core/template\.py"),
}
# (pattern name -> files that may name it): the hook forwarding stubs (until Phase 9), the share builder that still builds
# refs from before the move, and this test.
ALLOWED = {
    "*": {"tests/test_no_old_paths.py"},
    "python -m kb.": {"src/kb_distillery/share/build.py"},
    "tools/": {"src/kb_distillery/core/schema.py"},               # TOOLING_PATHS keeps tools/ for the stubs until Phase 9
    "backend/src or backend/tests": {"src/kb_distillery/share/build.py", "tests/share/test_share_app.py", "tests/share/test_share_versions.py", "pixi.toml"},
}
# The roadmap is the record of what was planned and done under the old names; it is not rewritten.
ALLOWED["meta-defaults/"] = {"docs/ROADMAP.md"}
ALLOWED["root skills/ folder, sync-skills or SKILL_TEMPLATE"] = {"docs/ROADMAP.md"}
ALLOWED["templates/ kit folder, template.toml, core.template or $KB_TEMPLATES_DIR"] = {"docs/ROADMAP.md"}
ALLOWED["keychain service thesis-kb-gmail"] = {"src/kb_distillery/config/userdir.py",      # the read-only lookup of the old name
                                               "tests/ops/test_notify.py", "tests/config/test_userdir.py"}
ALLOWED["~/.config/thesis-kb"] = {"tests/config/test_userdir.py", "src/kb_distillery/config/userdir.py"}
ALLOWED_PREFIXES = ("tools/", "docs/plans/", "scripts/qmd/package-lock.json")
ALLOWED_PREFIXES_FOR = {"tools/": ("web/src/",)}               # web/src/features/graph/tools/ is a real folder of the app
SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".zip", ".lock", ".svg")


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p and not p.endswith(SKIP_SUFFIX)]


RETIRED_FILES = ("src/kb_distillery/maintenance/fix_math.py", "src/kb_distillery/maintenance/rename_raw.py",
                 "src/kb_distillery/maintenance/daily_sync.py", "src/kb_distillery/maintenance/notify.py",
                 "src/kb_distillery/maintenance/export.py", "src/kb_distillery/report/", "src/kb_distillery/cli.py",
                 "tests/maintenance/", "tests/report/",
                 "src/kb_distillery/core/template.py", "tests/core/test_template.py", "tests/templates/",
                 "skills/", "src/kb_distillery/maintenance/")


class NoOldPathsTests(unittest.TestCase):
    def test_retired_files_are_gone(self):
        files = [p for p in tracked() if os.path.exists(os.path.join(ROOT, p))]   # a deletion is staged only at commit
        for old in RETIRED_FILES:
            self.assertEqual([p for p in files if p.startswith(old)], [], old)

    def test_old_directories_are_gone(self):
        files = tracked()
        for old in ("backend/src", "backend/tests", "frontend/", "kbs/", "templates/", "meta-defaults/", "skills/"):
            self.assertEqual([p for p in files if p.startswith(old)], [], old)

    def test_the_schema_no_longer_lists_the_retired_root_folders(self):
        from kb_distillery.core import schema
        for old in ("templates", "meta-defaults", "skills"):
            self.assertNotIn(old, schema.ROOT_DIRS)
            self.assertNotIn(old, schema.CODE_TOP_DIRS)
            self.assertNotIn(old + "/", schema.TOOLING_PATHS)

    def test_the_skills_live_in_the_kits_and_the_dev_skills_are_real_files(self):
        self.assertFalse(os.path.islink(os.path.join(ROOT, ".claude", "skills")))
        for rel in ("src/kb_distillery/kits/base/skills/query-knowledge/SKILL.md", "src/kb_distillery/kits/base/skills/_TEMPLATE.md",
                    "src/kb_distillery/kits/research/skills/build-researcher-profile/SKILL.md", ".claude/skills/infra-pr/SKILL.md",
                    "docs/guides/write-a-skill.md"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_the_kits_live_in_the_package(self):
        for rel in ("src/kb_distillery/kits/base/kit.toml", "src/kb_distillery/kits/research/kit.toml",
                    "src/kb_distillery/kits/base/defaults/flags.toml"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_no_tracked_file_names_a_retired_path_or_module(self):
        hits = []
        for rel in tracked():
            if rel.startswith(ALLOWED_PREFIXES) or rel in ALLOWED["*"]:
                continue
            try:
                with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
                    text = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for name, pat in RETIRED.items():
                if rel in ALLOWED.get(name, ()) or rel.startswith(ALLOWED_PREFIXES_FOR.get(name, ("\0",))):
                    continue
                m = pat.search(text)
                if m:
                    line = text.count("\n", 0, m.start()) + 1
                    hits.append(f"{rel}:{line}: {name}")
        self.assertEqual(hits, [], "retired layout strings:\n" + "\n".join(hits[:40]))


if __name__ == "__main__":
    unittest.main()
