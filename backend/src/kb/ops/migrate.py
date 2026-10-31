"""Schema migrations: in a schema/paradigm PR on an infra/* branch, or, for a kb that is its own git repo, on its main.

Each migration is backend/src/kb/migrations/NNNN_<name>.py defining:
    PRODUCES = (x, y)        # SCHEMA_VERSION after it has run
    def apply(root): ...      # idempotent; rewrites notes to the new rules
Applied migrations are recorded in meta/migrations/applied.tsv (id, date, version).
"""
import datetime
import importlib.util
import os
import re
import subprocess
import sys

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
from kb.core.schema import SCHEMA_VERSION
from kb.paths import MIGRATIONS_CODE_PATH

MIGRATIONS_DIR = os.path.join("meta", "migrations")      # vault side: applied.tsv


def _code_dirs(root):
    """Where migration code is found: the kb package, unless the vault root carries migration code of its
    own in meta/migrations (a fixture root, or a schema PR written against an older layout)."""
    local = os.path.join(root, MIGRATIONS_DIR)
    if os.path.isdir(local) and any(f[:4].isdigit() and f.endswith(".py") for f in os.listdir(local)):
        return [local]
    return [MIGRATIONS_CODE_PATH]


def _applied(root):
    path = os.path.join(root, MIGRATIONS_DIR, "applied.tsv")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        rows = [l.rstrip("\n").split("\t") for l in f if l.strip() and not l.startswith("id\t")]
    return {r[0]: r for r in rows}


def available(root):
    found = set()
    for d in _code_dirs(root):
        if os.path.isdir(d):
            found |= {f[:-3] for f in os.listdir(d) if f[:4].isdigit() and f.endswith(".py")}
    return sorted(found)


def pending_migrations(root):
    done = _applied(root)
    return [m for m in available(root) if m not in done]


def _load(root, mid):
    path = next((p for p in (os.path.join(d, f"{mid}.py") for d in _code_dirs(root)) if os.path.isfile(p)), None)
    spec = importlib.util.spec_from_file_location(mid, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def own_repo(root):
    """True when `root` is a knowledge base that is its own git repo (kb.toml at the top of its own checkout).
    `kbs/demo` is not: the engine repo tracks it, so it migrates in a schema PR like the engine does."""
    if not os.path.isfile(os.path.join(root, "kb.toml")):
        return False
    top = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return top.returncode == 0 and os.path.realpath(top.stdout.strip()) == os.path.realpath(root)


def _apply(root, pending):
    path = os.path.join(root, MIGRATIONS_DIR, "applied.tsv")
    new_file = not os.path.isfile(path)
    done = []
    for mid in pending:
        mod = _load(root, mid)
        produces = tuple(getattr(mod, "PRODUCES", SCHEMA_VERSION))
        if produces > tuple(SCHEMA_VERSION):
            raise RuntimeError(f"{mid} produces schema {produces} but SCHEMA_VERSION is {SCHEMA_VERSION} — bump it")
        mod.apply(root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            if new_file:
                f.write("id\tdate\tschema\n")
                new_file = False
            f.write(f"{mid}\t{datetime.date.today().isoformat()}\t{produces[0]}.{produces[1]}\n")
        done.append(mid)
        print(f"applied {mid} → schema {produces[0]}.{produces[1]}")
    return done


def _bump_kb_toml(root):
    """Set `[kb] schema_version` to SCHEMA_VERSION, keeping every comment and the rest of the file as written."""
    path = os.path.join(root, "kb.toml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new = re.sub(r'^(schema_version\s*=\s*)"[^"]*"', rf'\g<1>"{SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]}"', text,
                 count=1, flags=re.M)
    if new != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)


def _migrate_own_repo(root):
    """A kb repo has no engine PR to carry its migration, so it migrates on its own main: apply, bump kb.toml, then
    one `chore(schema)` commit (kb.toml + applied.tsv, both kb tooling) and, only if a migration rewrote notes, one
    `kb(refine)` step for them. The kb version follows by itself: the next step is kb-<x>.<y>.1 (commit_policy)."""
    from . import core
    core._require_main(root)
    pending = pending_migrations(root)
    ids = _apply(root, pending)
    _bump_kb_toml(root)
    version = f"{SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]}"
    core._commit_paths(root, ["kb.toml", os.path.join(MIGRATIONS_DIR, "applied.tsv")],
                       f"chore(schema): schema {version} ({', '.join(ids)})\n")
    print(f"committed chore(schema): schema {version}")
    if core.changed_paths(root)["knowledge"]:
        core.commit_op("refine", f"schema-{version.replace('.', '-')}", f"migrate notes to schema {version}", root=root)
    return ids


def run(root, branch, check=False):
    """Apply pending migrations in order. Returns the ids applied (or pending, with check)."""
    pending = pending_migrations(root)
    if check or not pending:
        return pending
    if not branch.startswith("infra/"):
        if branch == "main" and own_repo(root):
            return _migrate_own_repo(root)
        raise RuntimeError("migrations run inside a schema PR (infra/* branch), never on the engine's main")
    return _apply(root, pending)
