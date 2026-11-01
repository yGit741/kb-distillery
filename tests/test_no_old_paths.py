"""The retired layout (backend/, frontend/, tools/, kbs/demo, package `kb`) stays gone.

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
}
# (pattern name -> files that may name it): the hook forwarding stubs (until Phase 9), the share builder that still builds
# refs from before the move, and this test.
ALLOWED = {
    "*": {"tests/test_no_old_paths.py"},
    "python -m kb.": {"src/kb_distillery/share/build.py"},
    "tools/": {"src/kb_distillery/core/schema.py"},               # TOOLING_PATHS keeps tools/ for the stubs until Phase 9
    "backend/src or backend/tests": {"src/kb_distillery/share/build.py", "tests/share/test_share_app.py", "tests/share/test_share_versions.py", "pixi.toml"},
}
ALLOWED_PREFIXES = ("tools/", "docs/plans/", "scripts/qmd/package-lock.json")
ALLOWED_PREFIXES_FOR = {"tools/": ("web/src/",)}               # web/src/features/graph/tools/ is a real folder of the app
SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".zip", ".lock", ".svg")


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p and not p.endswith(SKIP_SUFFIX)]


class NoOldPathsTests(unittest.TestCase):
    def test_old_directories_are_gone(self):
        files = tracked()
        for old in ("backend/src", "backend/tests", "frontend/", "kbs/"):
            self.assertEqual([p for p in files if p.startswith(old)], [], old)

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
