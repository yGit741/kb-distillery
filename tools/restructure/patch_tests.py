"""Patches for tests whose fixtures depended on code living in the vault's meta/.

Pattern: temp git repos used to carry a stub `meta/lint.py` that ops ran as `<root>/meta/lint.py`. The
linter is a module of the installed package now, so those tests patch `kb.ops.core.run_lint` instead
(lint of a bare temp repo is not what they test) and commit a plain tooling file as their first commit.
"""

LINT_PATCH = ('{ind}_lint = {mock}("kb.ops.core.run_lint", return_value=None)  # lint of a bare temp repo is not under test\n'
              '{ind}_lint.start()\n{ind}self.addCleanup(_lint.stop)\n')


def register(add):
    add("backend/tests/ops/test_ops.py",
        ('        self.write("backend/src/kb/lint/lint.py", "import sys; sys.exit(0)\\n", mode="w")\n',
         LINT_PATCH.format(ind="        ", mock="patch") + '        self.write("meta/stub.py", "x = 1\\n", mode="w")\n'))
    add("backend/tests/ops/test_adopt.py",
        ('        write(self.root, "backend/src/kb/lint/lint.py", "import sys; sys.exit(0)\\n")\n',
         LINT_PATCH.format(ind="        ", mock="patch") + '        write(self.root, "meta/stub.py", "x = 1\\n")\n'))
    add("backend/tests/ops/test_hygiene.py",
        ('        os.makedirs(os.path.join(self.root, "meta"), exist_ok=True)\n'
         '        with open(os.path.join(self.root, "meta", "lint.py"), "w") as f:\n'
         '            f.write("import sys; sys.exit(0)\\n")\n'
         '        self.commit("backend/src/kb/lint/lint.py", None, "chore(init): lint stub")\n',
         LINT_PATCH.format(ind="        ", mock="patch") + '        self.commit("meta/stub.py", "x = 1", "chore(init): tooling stub")\n'))
    add("backend/tests/core/test_scopes.py",
        ('        files = dict()\n        files["backend/src/kb/lint/lint.py"] = "import sys; sys.exit(0)\\n"\n',
         LINT_PATCH.format(ind="        ", mock="mock.patch") + '        files = dict()\n        files["meta/stub.py"] = "x = 1\\n"\n'))
    add("backend/tests/share/test_share_deploy.py",
        ('        for rel, text in (("backend/src/kb/lint/lint.py", "import sys; sys.exit(0)\\n"), ("meta/log.md", "# log\\n"),',
         LINT_PATCH.format(ind="        ", mock="mock.patch") +
         '        for rel, text in (("meta/stub.py", "x = 1\\n"), ("meta/log.md", "# log\\n"),'))
    # git hooks in a temp repo: they now run `python3 -m kb.*` with PYTHONPATH=<repo>/backend/src, so the repo
    # carries a minimal kb package (the real commit_policy + schema, stub linters)
    add("backend/tests/migrations/test_migrations.py",
        ('from kb.paths import vault_root\n', 'from kb.paths import CODE_DIR, vault_root\n'),
        ('        os.makedirs(os.path.join(self.root, "meta"))\n'
         '        for name in ("commit_policy.py", "schema.py"):\n'
         '            shutil.copy(os.path.join(ROOT, "meta", name), os.path.join(self.root, "meta", name))\n'
         '        shutil.copytree(os.path.join(ROOT, "tools", "githooks"), os.path.join(self.root, "tools", "githooks"))\n'
         '        with open(os.path.join(self.root, "meta", "lint.py"), "w") as f:\n'
         '            f.write("import os, sys\\nsys.exit(1 if os.path.exists(\'LINT_FAIL\') else 0)\\n")\n'
         '        with open(os.path.join(self.root, "meta", "lint_skills.py"), "w") as f:\n'
         '            f.write("import sys; sys.exit(0)\\n")\n',
         '        kb = os.path.join(self.root, "backend", "src", "kb")\n'
         '        for rel in ("__init__.py", "paths.py", "core/__init__.py", "core/schema.py", "git/__init__.py",\n'
         '                    "git/commit_policy.py"):\n'
         '            os.makedirs(os.path.dirname(os.path.join(kb, rel)), exist_ok=True)\n'
         '            shutil.copy(os.path.join(CODE_DIR, rel), os.path.join(kb, rel))\n'
         '        shutil.copytree(os.path.join(ROOT, "tools", "githooks"), os.path.join(self.root, "tools", "githooks"))\n'
         '        os.makedirs(os.path.join(kb, "lint"))\n'
         '        for rel, text in (("__init__.py", ""),\n'
         '                          ("lint.py", "import os, sys\\nsys.exit(1 if os.path.exists(\'LINT_FAIL\') else 0)\\n"),\n'
         '                          ("lint_skills.py", "import sys; sys.exit(0)\\n")):\n'
         '            with open(os.path.join(kb, "lint", rel), "w") as f:\n'
         '                f.write(text)\n'))
    add("backend/tests/core/test_persons.py",
        ('        # the migration imports kb.ingest.researcher from the vault root\n'
         '        os.symlink(os.path.join(HERE, "ingest"), os.path.join(self.root, "backend", "src", "kb", "ingest"))\n'
         '        for name in ("schema.py", "persons.py"):\n'
         '            shutil.copy(os.path.join(HERE, name), os.path.join(self.root, "meta", name))\n', ''))
    add("backend/tests/services/test_chat_agent.py",
        ('"backend/src/kb/search/query.py candidates"', '"kb.search.query candidates"'))
    add("backend/tests/core/test_persons.py",
        ('from kb.paths import vault_root\nHERE = os.path.join(vault_root(), "meta")\n', 'from kb.paths import CODE_DIR as HERE\n'))
    add("backend/tests/share/test_share_build.py",
        ('sys.path.insert(0, sys.argv[1])\nfrom dashboard import explore_data\n', 'from kb.services import pages as explore_data\n'),
        ('import json,sys; sys.path.insert(0, sys.argv[1]); from dashboard import graph_data; ',
         'import json,sys; from kb.services import graph as graph_data; '))
    add("backend/tests/share/test_share_build.py",
        ('self.assertIn("no backend/src/kb/share/build.py", msg)', 'self.assertIn("no share builder", msg)'))

    # the e2e vault: the scratch vault carries the checkout's code as a symlinked kb package + PYTHONPATH
    add("backend/tests/ingest/test_pipeline_e2e.py",
        ('from kb.paths import vault_root\n', 'from kb.paths import CODE_DIR, vault_root\n'),
        ('DATA = os.path.join(META, "testdata", "e2e")',
         'DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "testdata", "e2e")'),
        ('    os.makedirs(os.path.join(root, "meta"))\n'
         '    for name in sorted(os.listdir(META)):\n'
         '        if name in NOT_CODE or name.startswith("."):\n'
         '            continue\n'
         '        os.symlink(os.path.join(META, name), os.path.join(root, "meta", name))\n',
         '    os.makedirs(os.path.join(root, "meta"))\n'
         '    for name in ("templates", "ops"):          # vault-side inputs the tools read\n'
         '        os.symlink(os.path.join(META, name), os.path.join(root, "meta", name))\n'
         '    os.makedirs(os.path.join(root, "backend", "src"))\n'
         '    os.symlink(CODE_DIR, os.path.join(root, "backend", "src", "kb"))     # the checkout\'s code\n'),
        ('"PYTHONHASHSEED": "0", "TZ": "UTC", "NO_PROXY": "*"}',
         '"PYTHONHASHSEED": "0", "TZ": "UTC", "NO_PROXY": "*",\n'
         '                    "PYTHONPATH": os.path.join(root, "backend", "src")}'),
        ('sys.path.insert(0, "meta")\n', ''),
        ('sys.path.insert(0, ".")\n', ''),
        ('from dashboard import graph_data, explore_data, digestion_data, corpus_data',
         'from kb.services import graph as graph_data, pages as explore_data, pipeline as digestion_data, corpus as corpus_data'))

    add("backend/tests/testdata/e2e/golden/transcript.json",
        ('sys.path.insert(0, \\"meta\\")\\nfrom dashboard import graph_data, explore_data, digestion_data, corpus_data',
         'from kb.services import graph as graph_data, pages as explore_data, pipeline as digestion_data, corpus as corpus_data'),
        ('sys.path.insert(0, \\".\\")\\n', ''))
    add("backend/tests/dashboard/test_graph_ui.py",
        ('from pathlib import Path\n\nDASH = Path(__file__).resolve().parent / "dashboard"',
         'from pathlib import Path\n\nfrom kb.paths import CODE_DIR\n\nDASH = Path(CODE_DIR) / "dashboard"'))
    add("backend/tests/dashboard/test_source_layer_ui.py",
        ('from kb.paths import vault_root\n', 'from kb.paths import CODE_DIR, vault_root\n'),
        ('STATIC = os.path.join(META, "dashboard", "static")', 'STATIC = os.path.join(CODE_DIR, "dashboard", "static")'))
    add("backend/tests/core/test_source_model.py",
        ('from kb.paths import vault_root\n', 'from kb.paths import CODE_DIR, vault_root\n'),
        ('MIGRATION = os.path.join(META, "migrations", "0008_source_model.py")',
         'MIGRATION = os.path.join(CODE_DIR, "migrations", "0008_source_model.py")'),
        ('        for name in os.listdir(META):           # the migration imports wikiio/ops from <root>/meta\n'
         '            if name in ("wikiio.py", "ops", "schema.py", "lint.py", "hubs.py", "books.py", "persons.py",\n'
         '                        "scopes.py", "graph.py"):\n'
         '                os.symlink(os.path.join(META, name), os.path.join(self.root, "meta", name))\n', ''))
