"""Patches for ops, migrations, notify, ship and friends: code that located files by position."""


def register(add):
    # migrations: the code lives in the package, applied.tsv stays in the vault (meta/migrations/).
    # A vault root may still carry migration files of its own (fixture roots, a schema PR in flight):
    # both places are searched, the package wins.
    add("backend/src/kb/ops/migrate.py",
        ('from kb.core.schema import SCHEMA_VERSION\n',
         'from kb.core.schema import SCHEMA_VERSION\nfrom kb.paths import MIGRATIONS_CODE_PATH\n'),
        ('MIGRATIONS_DIR = os.path.join("meta", "migrations")\n',
         'MIGRATIONS_DIR = os.path.join("meta", "migrations")      # vault side: applied.tsv\n'
         '\n\ndef _code_dirs(root):\n'
         '    """Where migration code is found: the kb package, unless the vault root carries migration code of its\n'
         '    own in meta/migrations (a fixture root, or a schema PR written against an older layout)."""\n'
         '    local = os.path.join(root, MIGRATIONS_DIR)\n'
         '    if os.path.isdir(local) and any(f[:4].isdigit() and f.endswith(".py") for f in os.listdir(local)):\n'
         '        return [local]\n'
         '    return [MIGRATIONS_CODE_PATH]\n'),
        ('def available(root):\n    d = os.path.join(root, MIGRATIONS_DIR)\n    if not os.path.isdir(d):\n        return []\n'
         '    return sorted(f[:-3] for f in os.listdir(d) if f[:4].isdigit() and f.endswith(".py"))\n',
         'def available(root):\n    found = set()\n    for d in _code_dirs(root):\n        if os.path.isdir(d):\n'
         '            found |= {f[:-3] for f in os.listdir(d) if f[:4].isdigit() and f.endswith(".py")}\n'
         '    return sorted(found)\n'),
        ('    spec = importlib.util.spec_from_file_location(mid, os.path.join(root, MIGRATIONS_DIR, f"{mid}.py"))\n',
         '    path = next((p for p in (os.path.join(d, f"{mid}.py") for d in _code_dirs(root)) if os.path.isfile(p)), None)\n'
         '    spec = importlib.util.spec_from_file_location(mid, path)\n'))
    add("backend/src/kb/git/ship.py",
        ('("tests", [sys.executable, "-m", "unittest", "discover", "-s", "meta", "-p", "test_*.py", "-t", "."]),',
         '("tests", [sys.executable, "-m", "pytest", "-q", "backend/tests"]),'))
    add("backend/src/kb/services/lifecycle.py",
        ('== "tools/githooks"', '== "tools/githooks"'))
    add("backend/src/kb/services/chat.py",
        ('PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")',
         'PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")'))
    add("backend/tests/services/test_scopes_ui.py",
        ('from pathlib import Path\n\nDASH = Path(__file__).resolve().parent / "dashboard"',
         'from pathlib import Path\n\nfrom kb.paths import CODE_DIR\n\nDASH = Path(CODE_DIR) / "dashboard"'))
    add("backend/tests/git/test_guard.py",
        ('GUARD = os.path.join(ROOT, "meta", "guard.py")', 'GUARD = ["-m", "kb.git.guard"]'),
        ('[sys.executable, GUARD]', '[sys.executable, *GUARD]'))
    add("backend/src/kb/git/guard.py",
        ('RAW_DIR, ROOT_DIRS, ROOT_FILES, ROOT_MD', 'CODE_TOP_DIRS, RAW_DIR, ROOT_DIRS, ROOT_FILES, ROOT_MD'),
        ('        allowed = top in (WIKI_DIR, SCHEMA_META_DIR) or rel in ROOT_MD\n',
         '        allowed = top in (WIKI_DIR, SCHEMA_META_DIR) or top in CODE_TOP_DIRS or rel in ROOT_MD\n'),
        ('markdown lives in wiki/ or meta/. "',
         'markdown lives in wiki/, meta/ or the code folders (backend/ skills/ tools/ share/ frontend/). "'))
    add("backend/src/kb/ops/core.py",
        ('    proc = subprocess.run([sys.executable, "-m", "kb.lint.lint"], cwd=root,\n                          capture_output=True, text=True)',
         '    proc = subprocess.run([sys.executable, "-m", "kb.lint.lint"], cwd=root, env=dict(os.environ, KB_ROOT=str(root)),\n                          capture_output=True, text=True)'))

    # dead code the sys.path removal leaves behind
    add("backend/src/kb/migrations/0006_person_v2.py",
        ('    for p in (os.path.join(root, "meta"), root):\n        pass\n', ''))
    add("backend/src/kb/ingest/session.py", ('            _meta = os.path.join(ROOT, "meta")\n', ''))
    add("backend/src/kb/distill/cli.py", ('            _meta = os.path.join(ROOT, "meta")\n', ''))

    add("backend/src/kb/migrations/0008_source_model.py",
        ('HERE = os.path.dirname(os.path.abspath(__file__))\n', 'from kb.paths import vault_root\n'),
        ('    meta = os.path.join(root, "meta")\n    from kb.core import wikiio', '    from kb.core import wikiio'),
        ('default=os.path.dirname(os.path.dirname(HERE))', 'default=vault_root()'))
