"""The retired layout (backend/, frontend/, tools/, kbs/demo, package `kb`) stays gone, and so do the Lane D moves:
`maintenance/{daily_sync,notify,export,fix_math,rename_raw}`, the top-level `report/` package, the per-user folder
`~/.config/thesis-kb` (now `~/.config/kb-distillery`, `config/userdir.py`) and the keychain service `thesis-kb-gmail`,
and the Lane C moves: `templates/` (now `src/kb_distillery/kits/<kit>/kit.toml`, read by `config/kit.py`) and
`meta-defaults/` (now `src/kb_distillery/kits/base/defaults/`), the root `skills/` folder with its `.claude/skills`
symlink, `pixi run sync-skills` and `SKILL_TEMPLATE.md` (now `src/kb_distillery/kits/<kit>/skills/`, real files in
`.claude/skills/`, `docs/guides/write-a-skill.md` and `kits/base/skills/_TEMPLATE.md`), and the Lane F move of `kb_distillery.share`
into `kb_distillery.publish.site` / `.cloudflare` (the Worker sources left the root `share/` for `publish/cloudflare/worker/`,
`publish/site_state.py` became `publish/site/state.py`, `tests/share/` became `tests/publish/cloudflare/`).

There are no import shims: a star-import shim breaks mock.patch, `python -m` and -W error filters. Instead this scan
fails on any tracked file that still names the old module or path strings. Inputs come from `git ls-files` only (the
user's knowledge bases and worktrees are on disk but untracked)."""
import os
import re
import subprocess
import unittest

from tests.needs_git import needs_git

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
    "scripts/kb-hooks (now the kit's src/kb_distillery/kits/base/hooks) or the install script and env.sh": re.compile(
        r"scripts/kb-hooks|install-kb-hooks\.sh|kb-hooks/env\.sh|\bKBD_DIR\b"),
    "templates/ kit folder, template.toml, core.template or $KB_TEMPLATES_DIR": re.compile(
        r"(?<![\w./-])templates/(?:starter|academic-research|<name>)|template\.toml|KB_TEMPLATES_DIR"
        r"|kb_distillery[./]core[./]template\b|core import template\b|core/template\.py"),
    "kb_distillery.share package (now publish/site and publish/cloudflare)": re.compile(
        r"kb_distillery[./]share\b|from kb_distillery import share\b|kb_distillery[./]publish[./]site_state\b|publish[./]site_state\b"
        r"|tests/share\b|tests\.share\b"),
    "root share/ Worker folder (now src/kb_distillery/publish/cloudflare/worker)": re.compile(
        r"(?<![\w./~-])share/(?:admin|auth|flags\.gen|package\.json|wrangler|\*\.test)|node --test share/"
        r"|(?<![\w])root_resource\(\"share\"\)|_data/share\b"),
    "Lane E cycle moves (vault.kit is config.kit)": re.compile(r"kb_distillery[./]vault[./]kit\b|vault import kit\b|tests/vault/test_kit"),
    "Lane E cycle moves (the graph snapshot and queries live in graph/, the publisher port in hosting/)": re.compile(
        r"kb_distillery[./]services[./](?:graph|raw_layer|schema)\b|services import (?:graph|raw_layer|schema)\b"
        r"|kb_distillery[./]publish[./](?:base|null|registry)\b|publish import (?:base|null|registry)\b"),
    "Lane E renames (core is now vault)": re.compile(
        r"kb_distillery[./]core\b|from kb_distillery import core\b|tests[/.]core\b|(?<![\w./-])core/(?:schema|links|wikiio|frontmatter)\.py"),
    "Lane E renames (kbconfig, paths and flags are now config/kb, config/paths and config/flags)": re.compile(
        r"kb_distillery[./](?:kbconfig|paths|flags)\b|from kb_distillery import[^\n#]*\b(?:kbconfig|paths|flags)\b"
        r"|tests/flags\b|tests\.flags\b|tests/vault/test_kbconfig"),
    "kb_distillery/prompts (now llm/prompts)": re.compile(r"kb_distillery[./]prompts\b|resource\(\"prompts\"\)"),
    "Lane E renames (ingest sources live in ingest/sources/<source>/)": re.compile(
        r"kb_distillery[./]ingest[./](?:youtube|blog|htmlmd|wordpress|mail|book|chat|chat_build|chat_merge|chat_render|chat_signal|chat_store|gdrive|researcher|backfill)\b|from kb_distillery\.ingest import[^\n#]*\b(?:blog|htmlmd|wordpress|mail|book|chat|chat_build|chat_merge|chat_render|chat_signal|chat_store|gdrive|researcher|backfill)\b"
        r"|(?<![\w.-])ingest/(?:youtube/|(?:blog|htmlmd|wordpress|mail|book|chat|chat_build|chat_merge|chat_render|chat_signal|chat_store|gdrive|researcher|backfill)\.py)|(?<![\w.-])ingest/test_(?:blog|wordpress|youtube|chat\w*|researcher|set_url)\.py"),
    "Lane E renames (web/e2e is now tests/e2e)": re.compile(r"web/e2e\b"),
    "Lane E renames (api is now server)": re.compile(
        r"kb_distillery[./]api\b|from kb_distillery import[^\n#]*\bapi\b|(?<![\w/.-])tests/api\b|\{api,services\}"),
    "Lane E renames (summaries is now digest)": re.compile(r"kb_distillery[./]summaries\b|from kb_distillery import[^\n#]*\bsummaries\b|tests/vault/test_summary\b"),
}
# (pattern name -> files that may name it): the tools/ entry of TOOLING_PATHS (until Phase 9), the share builder that still builds
# refs from before the move, and this test.
ALLOWED = {
    "*": {"tests/test_no_old_paths.py",
          "CHANGELOG.md"},      # a changelog names the old paths to say where they went
    "tools/": {"src/kb_distillery/vault/schema.py"},               # TOOLING_PATHS keeps tools/ for the two remaining stubs until Phase 9
    "python -m kb.": {"src/kb_distillery/publish/site/build.py"},
    "backend/src or backend/tests": {"src/kb_distillery/publish/site/build.py", "tests/publish/cloudflare/test_share_app.py",
                                     "tests/publish/cloudflare/test_share_versions.py", "pixi.toml"},
    # the build still runs an OLDER viewer ref with that ref's own module path (build.APP_GENERATIONS), and the deny rules keep
    # the old patterns so the deny never weakens
    "kb_distillery.share package (now publish/site and publish/cloudflare)": {
        "src/kb_distillery/publish/site/build.py", ".claude/settings.json", "tests/publish/cloudflare/test_share_versions.py",
        "tests/publish/cloudflare/test_share_build.py", "docs/ROADMAP.md", "docs/phase-7-audit.md"},
}
# The roadmap is the record of what was planned and done under the old names; it is not rewritten.
ALLOWED["meta-defaults/"] = {"docs/ROADMAP.md"}
ALLOWED["root skills/ folder, sync-skills or SKILL_TEMPLATE"] = {"docs/ROADMAP.md"}
ALLOWED["Lane E renames (core is now vault)"] = {"docs/ROADMAP.md"}
ALLOWED["kb_distillery/prompts (now llm/prompts)"] = {"docs/ROADMAP.md"}
ALLOWED["Lane E renames (summaries is now digest)"] = {"docs/ROADMAP.md"}
ALLOWED["Lane E renames (api is now server)"] = {"docs/ROADMAP.md"}
ALLOWED["Lane E renames (web/e2e is now tests/e2e)"] = {"docs/ROADMAP.md"}
ALLOWED["Lane E renames (ingest sources live in ingest/sources/<source>/)"] = {"docs/ROADMAP.md"}
ALLOWED["Lane E renames (kbconfig, paths and flags are now config/kb, config/paths and config/flags)"] = {"docs/ROADMAP.md"}
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


RETIRED_FILES = ("src/kb_distillery/share/", "src/kb_distillery/publish/site_state.py", "share/", "tests/share/",
                 "src/kb_distillery/maintenance/fix_math.py", "src/kb_distillery/maintenance/rename_raw.py",
                 "src/kb_distillery/maintenance/daily_sync.py", "src/kb_distillery/maintenance/notify.py",
                 "src/kb_distillery/maintenance/export.py", "src/kb_distillery/report/", "src/kb_distillery/cli.py",
                 "tests/maintenance/", "tests/report/",
                 "src/kb_distillery/core/template.py", "tests/core/test_template.py", "tests/templates/",
                 "scripts/install-kb-hooks.sh", "scripts/kb-hooks/env.sh", "scripts/kb-hooks/kb-guard.sh",
                 "scripts/kb-hooks/kb-git-guard.sh", "scripts/kb-hooks/claude-settings.json",
                 "scripts/kb-hooks/", "tools/kb-hooks/",          # the forwarding stubs, deleted with the knowledge move (C.6)
                 "skills/", "src/kb_distillery/maintenance/",
                 "src/kb_distillery/vault/kit.py", "tests/vault/test_kit.py", "tests/vault/test_kit_contract.py",
                 "src/kb_distillery/services/graph.py", "src/kb_distillery/services/raw_layer.py",
                 "src/kb_distillery/services/schema.py", "src/kb_distillery/publish/base.py",
                 "src/kb_distillery/publish/null.py", "src/kb_distillery/publish/registry.py",
                 "src/kb_distillery/core/", "tests/core/",
                 "src/kb_distillery/kbconfig.py", "src/kb_distillery/paths.py", "src/kb_distillery/flags/", "tests/flags/",
                 "tests/vault/test_kbconfig.py", "src/kb_distillery/prompts/",
                 "src/kb_distillery/summaries/", "tests/vault/test_summary.py", "src/kb_distillery/api/", "tests/api/", "web/e2e/",
                 "src/kb_distillery/ingest/youtube/", *(f"src/kb_distillery/ingest/{m}.py" for m in (
                     "blog", "htmlmd", "wordpress", "mail", "book", "chat", "chat_build", "chat_merge", "chat_render", "chat_signal",
                     "chat_store", "gdrive", "researcher", "backfill")),
                 *(f"tests/ingest/test_{m}.py" for m in ("blog", "wordpress", "youtube", "chat", "chat_kb", "chat_merge", "chat_store",
                                                         "researcher", "set_url")))


@needs_git
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
        from kb_distillery.vault import schema
        for old in ("templates", "meta-defaults", "skills"):
            self.assertNotIn(old, schema.ROOT_DIRS)
            self.assertNotIn(old, schema.CODE_TOP_DIRS)
            self.assertNotIn(old + "/", schema.TOOLING_PATHS)

    def test_the_skills_live_in_the_kits_and_the_dev_skills_are_real_files(self):
        self.assertFalse(os.path.islink(os.path.join(ROOT, ".claude", "skills")))
        owner = (".claude/skills/infra-pr/SKILL.md",) if os.path.isdir(os.path.join(ROOT, ".claude", "skills")) else ()   # export-ignored from the public repo
        for rel in ("src/kb_distillery/kits/base/skills/query-knowledge/SKILL.md", "src/kb_distillery/kits/base/skills/_TEMPLATE.md",
                    "src/kb_distillery/kits/research/skills/build-researcher-profile/SKILL.md", *owner,
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
