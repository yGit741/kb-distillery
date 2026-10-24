"""Schema migrations — run only inside a schema/paradigm PR (on an infra/* branch).

Each migration is backend/src/kb/migrations/NNNN_<name>.py defining:
    PRODUCES = (x, y)        # SCHEMA_VERSION after it has run
    def apply(root): ...      # idempotent; rewrites notes to the new rules
Applied migrations are recorded in meta/migrations/applied.tsv (id, date, version).
"""
import datetime
import importlib.util
import os
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


def run(root, branch, check=False):
    """Apply pending migrations in order. Returns the ids applied (or pending, with check)."""
    pending = pending_migrations(root)
    if check or not pending:
        return pending
    if not branch.startswith("infra/"):
        raise RuntimeError("migrations run inside a schema PR (infra/* branch), never on main")
    path = os.path.join(root, MIGRATIONS_DIR, "applied.tsv")
    new_file = not os.path.isfile(path)
    done = []
    for mid in pending:
        mod = _load(root, mid)
        produces = tuple(getattr(mod, "PRODUCES", SCHEMA_VERSION))
        if produces > tuple(SCHEMA_VERSION):
            raise RuntimeError(f"{mid} produces schema {produces} but SCHEMA_VERSION is {SCHEMA_VERSION} — bump it")
        mod.apply(root)
        with open(path, "a", encoding="utf-8") as f:
            if new_file:
                f.write("id\tdate\tschema\n")
                new_file = False
            f.write(f"{mid}\t{datetime.date.today().isoformat()}\t{produces[0]}.{produces[1]}\n")
        done.append(mid)
        print(f"applied {mid} → schema {produces[0]}.{produces[1]}")
    return done
