"""Hand-written substitutions the generic codemod cannot derive, keyed by the file's NEW path.

Each entry is (old, new) over exact text. `apply` is tolerant so the script can be re-run after main moved:
  * `old` present      -> replaced
  * `new` already there -> counted as applied
  * neither            -> reported as a PATCH MISS (main changed that code; adapt the entry)
An entry may also be ("re:<pattern>", replacement) for a regex over the whole file.
"""
import os
import re

from layout import PKG, TESTS

P = f"{PKG}"

# files (not moved) whose references the generic text rules rewrite, by phase:
#   move: pixi.toml (the tasks must run the moved modules)   refs: agent/CI/hook configs   docs: markdown docs
PHASE_FILES = {
    "move": ["pixi.toml"],
    "refs": [".gitignore", ".claude/settings.json", ".cursor/hooks.json", ".cursor/hooks/block-git-write.sh"],
    "docs": ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md", "meta/automation-daily-sync.md", "meta/web-clipper.md"],
}


def STATIC_TEXT_FILES(root, phase="all"):
    phases = ["move", "refs", "docs"] if phase == "all" else [phase]
    out = []
    for ph in phases:
        out += PHASE_FILES[ph]
        if ph == "refs":
            for sub in (".cursor/rules", ".github/workflows", ".vscode"):
                d = os.path.join(root, sub)
                if os.path.isdir(d):
                    out += [f"{sub}/{fn}" for fn in sorted(os.listdir(d))]
    return out


# sys.path.insert allowed to remain (path: reason)
SYS_PATH_ALLOWED = {"backend/tests/share/test_share_scaffold.py"}   # puts a temp package dir on sys.path on purpose

PATCHES = {}


def PATCHED_NEW_FILES():
    """Moved files that carry patches (re-applied on a re-run, when main changed them after the first run)."""
    return sorted(p for p in PATCHES if p.startswith(("backend/", "tools/", "share/", "skills/")))


def apply(newpath, text):
    entries = PATCHES.get(newpath, [])
    n, misses = 0, []
    for old, new in entries:
        if isinstance(old, str) and old.startswith("re:"):
            rx = re.compile(old[3:], re.M)
            if rx.search(text):
                text, k = rx.subn(new, text)
                n += k
            elif not misses_ok(new, text):
                misses.append(old)
            continue
        if new and new in text:
            continue                      # already applied (checked first: `new` may contain `old`)
        if old in text:
            n += text.count(old)
            text = text.replace(old, new)
        elif new == "":
            continue                      # a deletion whose target is already gone
        else:
            misses.append(old)
    return text, n, misses


def misses_ok(new, text):
    return new in text and new != ""


def add(path, *pairs):
    PATCHES.setdefault(path, []).extend(pairs)


PYP = 'export PYTHONPATH="$root/backend/src${PYTHONPATH:+:$PYTHONPATH}"\n'

# ---- git hooks, agent hooks -------------------------------------------------------------------
add("tools/githooks/commit-msg",
    ('exec python3 "$root/backend/src/kb/git/commit_policy.py" msg "$1"',
     PYP + 'exec python3 -m kb.git.commit_policy msg "$1"'))
add("tools/githooks/pre-push",
    ('exec python3 "$root/backend/src/kb/git/commit_policy.py" push "$@"',
     PYP + 'exec python3 -m kb.git.commit_policy push "$@"'))
add("tools/githooks/pre-commit",
    ('root="$(git rev-parse --show-toplevel)"\n', 'root="$(git rev-parse --show-toplevel)"\n' + PYP),
    ('python3 "$root/backend/src/kb/lint/lint.py" ||', 'python3 -m kb.lint.lint ||'),
    ('python3 "$root/backend/src/kb/lint/lint_skills.py" ||', 'python3 -m kb.lint.lint_skills ||'))
add(".claude/settings.json",
    ('python3 \\"$CLAUDE_PROJECT_DIR/backend/src/kb/git/guard.py\\"',
     'PYTHONPATH=\\"$CLAUDE_PROJECT_DIR/backend/src\\" python3 -m kb.git.guard'),
    ('python3 \\"$CLAUDE_PROJECT_DIR/backend/src/kb/git/merge_nudge.py\\"',
     'PYTHONPATH=\\"$CLAUDE_PROJECT_DIR/backend/src\\" python3 -m kb.git.merge_nudge'))
add(".cursor/hooks.json",
    ('"command": "python3 -m kb.git.guard"', '"command": "PYTHONPATH=backend/src python3 -m kb.git.guard"'),
    ('git|gh |pixi run|meta/daily_sync|meta/ship|meta/curate_history|meta\\\\.ops',
     'git|gh |pixi run|kb\\\\.maintenance\\\\.daily_sync|kb\\\\.git\\\\.ship|kb\\\\.git\\\\.curate_history|kb\\\\.ops'))
add(".cursor/hooks/block-git-write.sh",
    ('exec python3 "$root/backend/src/kb/git/git_guard.py"',
     'PYTHONPATH="$root/backend/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m kb.git.git_guard'))
add("tools/launch.sh",
    ('find meta -name __pycache__ -type d -prune', 'find backend -name __pycache__ -type d -prune'))

# ---- pixi.toml ------------------------------------------------------------------------------------
add("pixi.toml",
    ('test-skills = "python -m unittest meta.test_skills"', 'test-skills = "pytest backend/tests/lint/test_skills.py"'),
    ('test = "python -m unittest discover -s meta -p test_*.py -t ."', 'test = "pytest backend/tests"'),
    ('harness = "python -m meta.tests.harness.run_pipeline"',
     'harness = { cmd = "python -m tests.harness.run_pipeline", env = { PYTHONPATH = "backend" } }'),
    ('harness-invariants = "python -m meta.tests.harness.vault_invariants"',
     'harness-invariants = { cmd = "python -m tests.harness.vault_invariants", env = { PYTHONPATH = "backend" } }'),
    ('harness-bite = "python -m meta.tests.harness.harness_bite"',
     'harness-bite = { cmd = "python -m tests.harness.harness_bite", env = { PYTHONPATH = "backend" } }'),
    ('truststore = ">=0.9"\n', 'truststore = ">=0.9"\npytest = ">=8"\n'),
    ('[pypi-dependencies]\n', '[pypi-dependencies]\nkb = { path = "backend", editable = true }\n'))

# ---- command allowlists -------------------------------------------------------------------------
add("backend/src/kb/git/git_guard.py",
    ('ALLOW_MODULES = {"kb.ops", "kb.maintenance.daily_sync", "kb.git.ship"}',
     'ALLOW_MODULES = {"kb.ops", "kb.maintenance.daily_sync", "kb.git.ship", "kb.git.curate_history"}'))
_CA = "backend/src/kb/services/chat_agent.py"
add(_CA,
    ('BASH_FORBIDDEN_CHARS = set(',
     '# query / semfind run as modules (any arguments); the scope rules below narrow them\nBASH_ANY_MODULES = {"kb.search.query", "kb.search.semfind"}\nBASH_FORBIDDEN_CHARS = set('),
    ('    if toks[1] == "-m":\n        return len(toks) >= 4 and (toks[2], toks[3]) in BASH_MODULES\n    script = toks[1]',
     '    if toks[1] == "-m":\n        if len(toks) >= 3 and toks[2] in BASH_ANY_MODULES:\n            return True\n        return len(toks) >= 4 and (toks[2], toks[3]) in BASH_MODULES\n    script = toks[1]'),
    ('    if mod == "backend/src/kb/search/semfind.py":', '    if mod in ("kb.search.semfind", "backend/src/kb/search/semfind.py"):'),
    ('    if mod == "backend/src/kb/search/query.py":', '    if mod in ("kb.search.query", "backend/src/kb/search/query.py"):'),
    (r'(?:-m\s+meta\.explore_raw|(?:\S*/)?meta/explore_raw\.py)', r'(?:-m\s+kb\.search\.explore_raw|(?:\S*/)?backend/src/kb/search/explore_raw\.py)'),
    (r'(?:-m\s+meta\.ingest\s+|meta/(?:query|semfind)\.py\s+)', r'(?:-m\s+kb\.ingest\s+|-m\s+kb\.search\.(?:query|semfind)\s+|(?:\S*/)?backend/src/kb/search/(?:query|semfind)\.py\s+)'))

# ---- skills lint / sync ---------------------------------------------------------------------------
_LS = "backend/src/kb/lint/lint_skills.py"
add(_LS,
    ('try:\n    from kb.maintenance.sync_skills import DEPRECATED\nexcept ImportError:\n    from kb.maintenance.sync_skills import DEPRECATED\n\nfrom kb.paths import vault_root\nROOT = vault_root()\nMETA = os.path.join(ROOT, "meta")\nSKILLS_ROOT = os.path.join(META, "skills")',
     'from kb.maintenance.sync_skills import DEPRECATED\nfrom kb.paths import CODE_DIR, vault_root\n\nROOT = vault_root()\nSKILLS_ROOT = os.path.join(ROOT, "skills")'),
    ('def _meta_packages() -> frozenset[str]:\n    pkgs: set[str] = set()\n    for name in os.listdir(META):\n        pkg = os.path.join(META, name)\n        if os.path.isdir(pkg) and (\n            os.path.isfile(os.path.join(pkg, "__main__.py"))\n            or name in ("ingest", "distill", "dashboard")\n        ):\n            pkgs.add(name)\n    return frozenset(pkgs)\n',
     'def _kb_modules() -> frozenset[str]:\n    """Every runnable `python -m kb.<dotted>` target: modules and packages with a __main__."""\n    mods: set[str] = set()\n    for dp, dns, fns in os.walk(CODE_DIR):\n        dns[:] = [d for d in dns if d != "__pycache__"]\n        rel = os.path.relpath(dp, CODE_DIR)\n        prefix = "kb" if rel == "." else "kb." + rel.replace(os.sep, ".")\n        if "__main__.py" in fns:\n            mods.add(prefix)\n        for fn in fns:\n            if fn.endswith(".py") and fn not in ("__init__.py", "__main__.py") and not fn[:4].isdigit():\n                mods.add(f"{prefix}.{fn[:-3]}")\n    return frozenset(mods)\n'),
    ('os.path.join(META, "ingest", "cli.py")', 'os.path.join(CODE_DIR, "ingest", "cli.py")'),
    ('os.path.join(META, "distill", "cli.py")', 'os.path.join(CODE_DIR, "distill", "cli.py")'),
    ('META_PACKAGES = _meta_packages()', 'KB_MODULES = _kb_modules()'),
    ('    m = re.match(r"python3 -m meta\\.(\\w+)(?:\\s|$)", line)\n    if m:\n        pkg = m.group(1)\n        if pkg not in META_PACKAGES:\n            err(rel_path, f"unknown meta package: {pkg}")\n        return\n\n    m = re.match(r"python3 meta/([\\w_]+)\\.py", line)\n    if m:\n        script = os.path.join(META, f"{m.group(1)}.py")\n        if not os.path.isfile(script):\n            err(rel_path, f"missing script: meta/{m.group(1)}.py")\n        return\n',
     '    m = re.match(r"python3 -m (kb(?:\\.\\w+)*)(?:\\s|$)", line)\n    if m:\n        if m.group(1) not in KB_MODULES:\n            err(rel_path, f"unknown module: {m.group(1)}")\n        return\n'))
add("backend/src/kb/maintenance/sync_skills.py",
    ('SRC = os.path.join(ROOT, "meta", "skills")', 'SRC = os.path.join(ROOT, "skills")'))


import patch_share  # noqa: E402
patch_share.register(add)

# ---- schema: the new top-level folders ------------------------------------------------------------
add("backend/src/kb/core/schema.py",
    ('ROOT_DIRS = frozenset({WIKI_DIR, RAW_DIR, THINK_DIR, META_DIR, QUARANTINE_DIR, FRONTEND_DIR})',
     '# Code and tooling folders beside the vault content (tooling lane; see TOOLING_PATHS).\nCODE_TOP_DIRS = frozenset({"backend", "frontend", "share", "skills", "tools"})\nROOT_DIRS = frozenset({WIKI_DIR, RAW_DIR, THINK_DIR, META_DIR, QUARANTINE_DIR, FRONTEND_DIR}) | CODE_TOP_DIRS'),
    ('    "meta/",\n    "README.md",', '    "meta/",\n    "backend/",\n    "share/",\n    "skills/",\n    "tools/",\n    "README.md",'))

add("backend/src/kb/services/pipeline.py",
    ('CODE_DIRS = ("meta", "backend/src/kb/dashboard", "backend/src/kb/dashboard/static", "backend/src/kb/ingest")',
     'CODE_DIRS = ("backend/src/kb", "backend/src/kb/core", "backend/src/kb/dashboard", "backend/src/kb/dashboard/static",\n             "backend/src/kb/ingest", "backend/src/kb/ops", "backend/src/kb/services")'))
import patch_ops  # noqa: E402
patch_ops.register(add)
import patch_harness  # noqa: E402
patch_harness.register(add)
import patch_docs  # noqa: E402
patch_docs.register(add)
import patch_tests  # noqa: E402
patch_tests.register(add)
