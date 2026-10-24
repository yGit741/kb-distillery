"""Patches for the pipeline harness (backend/tests/harness): code layout references only.

The scratch vault now carries a copy of the `kb` package under backend/src/kb and every command runs with
PYTHONPATH=<scratch>/backend/src, so the vault's own code (not the checkout's editable install) runs.
"""

H = "backend/tests/harness/"


def register(add):
    add(H + "fixture_vault.py",
        ('META_SRC = Path(__file__).resolve().parents[2]          # the meta/ directory of this checkout\n',
         'CHECKOUT = Path(__file__).resolve().parents[3]           # this checkout (backend/tests/harness/ -> repo root)\n'
         'CODE_SRC = CHECKOUT / "backend" / "src" / "kb"           # the tool code (package kb)\n'
         'META_SRC = CHECKOUT / "meta"                             # vault metadata that is also tooling input\n'),
        ('# Everything under meta/ is code except these (vault DATA, docs, workflows, harness itself).\n'
         'CODE_EXCLUDE = {"corpus.tsv", "coherence-warnings.tsv", "aliases.tsv", "log.md", "thesis.md", "chats", "migration",\n'
         '                "skills", "launchd", "githooks", "tests", "raw-renames.tsv", "automation-daily-sync.md",\n'
         '                "web-clipper.md", "__pycache__"}\n',
         '# meta/ holds vault data only now; the scratch vault copies just these (templates the writers read, ops config).\n'
         'META_COPY = ("templates", "ops")\n'),
        ('    for src in sorted(META_SRC.iterdir()):\n'
         '        if src.name in CODE_EXCLUDE or src.name.startswith(".") or src.name.startswith("test_"):\n'
         '            continue\n'
         '        if src.is_dir():\n'
         '            shutil.copytree(src, meta / src.name, ignore=CODE_IGNORE)\n'
         '        else:\n'
         '            shutil.copy2(src, meta / src.name)\n',
         '    shutil.copytree(CODE_SRC, root / "backend" / "src" / "kb", ignore=CODE_IGNORE)\n'
         '    for name in META_COPY:\n'
         '        if (META_SRC / name).is_dir():\n'
         '            shutil.copytree(META_SRC / name, meta / name, ignore=CODE_IGNORE)\n'))
    add(H + "run_pipeline.py",
        ('sys.path.insert(0, "meta")\n', ''),
        ('from dashboard import chat_data, explore_data, graph_data',
         'from kb.services import chat as chat_data, pages as explore_data, graph as graph_data'),
        ('from ingest import chat_build, chat_render', 'from kb.ingest import chat_build, chat_render'),
        ('        e.update(PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0", NO_COLOR="1")',
         '        e.update(PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0", NO_COLOR="1",\n'
         '                 PYTHONPATH=str(self.root / "backend" / "src"))     # the scratch vault runs its own copy of kb'),
        ('self.cmd("backend/src/kb/lint/lint.py", expect=expect)', 'self.cmd("-m", "kb.lint.lint", expect=expect)'))
    add(H + "vault_invariants.py",
        ('sys.path.insert(0, "meta")\n', ''),
        ('from dashboard import explore_data, graph_data', 'from kb.services import pages as explore_data, graph as graph_data'),
        ('        env["PYTHONDONTWRITEBYTECODE"] = "1"\n',
         '        env["PYTHONDONTWRITEBYTECODE"] = "1"\n        env["PYTHONPATH"] = str(copy / "backend" / "src")     # the measured vault runs its own code\n'),
        ('[sys.executable, "backend/src/kb/lint/lint.py"]', '[sys.executable, "-m", "kb.lint.lint"]'))
