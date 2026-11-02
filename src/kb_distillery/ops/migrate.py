"""Schema migrations: in a schema/paradigm PR on an infra/* branch, or, for a kb that is its own git repo, on its main.

Each migration is src/kb_distillery/migrations/NNNN_<name>.py defining:
    PRODUCES = (x, y)        # SCHEMA_VERSION after it has run
    def apply(root): ...      # idempotent; rewrites notes to the new rules
Applied migrations are recorded in meta/migrations/applied.tsv (id, date, version).
"""
import contextlib
import datetime
import io
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

from kb_distillery.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
from kb_distillery.core.schema import LEGACY_INDEX_REL, LEGACY_LOG_REL, SCHEMA_VERSION, is_index_path
from kb_distillery.paths import MIGRATIONS_CODE_PATH

MIGRATIONS_DIR = os.path.join("meta", "migrations")      # vault side: applied.tsv


class MigrateError(RuntimeError):
    """A refusal with a message for the owner (printed without a traceback by `ops migrate`)."""


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
    """True when `root` is a knowledge base that is its own repo (kb.toml at the top of its own checkout, and
    not the shared think repo). `examples/demo` is not: the engine repo tracks it, so it migrates in a schema PR."""
    from kb_distillery.git.commit_policy import _is_kb_repo
    if not _is_kb_repo(root):
        return False
    top = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return top.returncode == 0 and os.path.realpath(top.stdout.strip()) == os.path.realpath(root)


from kb_distillery.migrations._tree import _restore, _snapshot, link_bulk


def _apply(root, pending):
    """Run every pending migration, then record them. All or nothing: if one raises, the kb is put back exactly as it
    was (files a migration wrote are restored) and no applied.tsv row is written, so a rerun starts clean."""
    path = os.path.join(root, MIGRATIONS_DIR, "applied.tsv")
    mods = []
    for mid in pending:
        mod = _load(root, mid)
        produces = tuple(getattr(mod, "PRODUCES", SCHEMA_VERSION))
        if produces > tuple(SCHEMA_VERSION):
            raise RuntimeError(f"{mid} produces schema {produces} but SCHEMA_VERSION is {SCHEMA_VERSION} — bump it")
        mods.append((mid, mod, produces))
    with tempfile.TemporaryDirectory(prefix="kb-migrate-snap-") as snap:
        _snapshot(root, snap)
        try:
            for mid, mod, produces in mods:
                mod.apply(root)
                print(f"ran {mid} → schema {produces[0]}.{produces[1]}")
        except BaseException:
            _restore(root, snap)
            print("migration failed: the kb was put back exactly as it was; nothing is recorded")
            raise
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new_file = not os.path.isfile(path)
    with open(path, "a", encoding="utf-8") as f:
        if new_file:
            f.write("id\tdate\tschema\n")
        for mid, _mod, produces in mods:
            f.write(f"{mid}\t{datetime.date.today().isoformat()}\t{produces[0]}.{produces[1]}\n")
    for mid, _mod, produces in mods:
        print(f"applied {mid} → schema {produces[0]}.{produces[1]}")
    return [m for m, _, _ in mods]


def preflight(root, bump=False):
    """Everything `ops migrate` would do, on a throwaway copy of the kb (raw/ linked, not copied): apply the pending
    migrations, bump kb.toml, then run lint and okf-check on the result. Returns (ids, findings): findings is every
    ERROR line the two print, [] when the migrated kb would pass. The real kb is never written."""
    pending = pending_migrations(root)
    with tempfile.TemporaryDirectory(prefix="kb-migrate-pre-") as tmp:
        copy = os.path.join(tmp, os.path.basename(os.path.abspath(root)) or "kb")
        os.makedirs(copy)
        _snapshot(root, copy)
        link_bulk(root, copy)
        with contextlib.redirect_stdout(io.StringIO()):          # the copy's progress is not the kb's
            ids = _apply(copy, pending)
        if bump:
            _bump_kb_toml(copy)
        env = dict(os.environ, KB_ROOT=copy)
        env.pop("KB", None)
        findings = []
        mods = ("kb_distillery.lint.lint", "kb_distillery.lint.okf_check") if os.path.isfile(os.path.join(copy, "kb.toml")) else ()
        for mod in mods:
            proc = subprocess.run([sys.executable, "-m", mod], cwd=copy, env=env, capture_output=True, text=True)
            lines = [l for l in (proc.stdout or "").splitlines() if l.startswith("ERROR")]
            if proc.returncode != 0 and not lines:
                lines = [f"ERROR {mod} failed: " + " | ".join(((proc.stdout or "") + (proc.stderr or "")).splitlines()[-3:])]
            findings += lines
    return ids, findings


def check_before_writing(root, dry_run=False, bump=False):
    """Refuse a migration whose result would fail lint or okf-check, listing every finding, before anything is written
    or committed. The kb must fix those pages first, then migrate."""
    ids, findings = preflight(root, bump)
    if findings:
        raise MigrateError(f"{'dry run: ' if dry_run else ''}migrating {', '.join(ids) or 'kb.toml'} would leave the kb failing "
                           f"lint/okf-check ({len(findings)} findings); fix these first, nothing was written:\n"
                           + "\n".join(findings))
    if dry_run:
        print(f"dry run: would apply {', '.join(ids) or 'nothing'}; lint and okf-check pass on the result")
    return ids


def _want():
    return f"{SCHEMA_VERSION[0]}.{SCHEMA_VERSION[1]}"


def _kb_toml_version(root):
    import tomllib
    with open(os.path.join(root, "kb.toml"), "rb") as f:
        return str(tomllib.load(f).get("kb", {}).get("schema_version", ""))


def _bump_kb_toml(root):
    """Set `[kb] schema_version` to SCHEMA_VERSION in place (comments and every other table untouched). The new text
    is parsed and checked before it is written, so a value the edit could not reach raises instead of committing."""
    import tomllib
    path = os.path.join(root, "kb.toml")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    head = re.search(r"^\[kb\]\s*$", text, re.M)
    if not head:
        raise RuntimeError("kb.toml has no [kb] table")
    nxt = re.search(r"^\[", text[head.end():], re.M)
    stop = head.end() + nxt.start() if nxt else len(text)
    seg, n = re.subn(r"""^(\s*schema_version\s*=\s*)(["'])[^"']*\2""", rf'\g<1>"{_want()}"', text[head.end():stop],
                     count=1, flags=re.M)
    if not n:
        raise RuntimeError('kb.toml: no quoted `schema_version = "x.y"` under [kb] — set it by hand')
    new = text[:head.end()] + seg + text[stop:]
    if str(tomllib.loads(new).get("kb", {}).get("schema_version")) != _want():
        raise RuntimeError("kb.toml: schema_version did not take the new value — set it by hand")
    if new != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)


def _require_clean_notes(root):
    from . import core
    ignore = set(core.GENERATED_KNOWLEDGE) | {core.LOG_PATH}
    legacy = {LEGACY_INDEX_REL, LEGACY_LOG_REL}       # pre-1.7 places: a dirty one is lint/ops output, and migration 0015 deletes them
    stray = sorted(p for p in core.changed_paths(root)["knowledge"] if p not in ignore and p not in legacy and p != "kb.toml"
                   and not is_index_path(p))
    if stray:
        raise RuntimeError("commit or discard these first, a migration must start from clean notes: "
                           + ", ".join(stray[:5]) + (" …" if len(stray) > 5 else ""))


def _migrate_own_repo(root):
    """A kb repo has no engine PR to carry its migration, so it migrates on its own main, under the ops lock:
    apply, bump kb.toml, then one `chore(schema)` commit (kb.toml + applied.tsv, both kb tooling), pushed; and, only
    if a migration rewrote notes, one `kb(refine)` step for them. Notes must be clean first, so everything dirty
    afterwards is the migration's. Resumable: rerun after a failure and it finishes the bump and the commit even
    with nothing pending. The next kb step is then kb-<x>.<y>.1 (commit_policy.next_version)."""
    from . import core
    core._require_main(root)
    ignore = set(core.GENERATED_KNOWLEDGE) | {core.LOG_PATH}
    applied = os.path.join(MIGRATIONS_DIR, "applied.tsv")
    with core.ops_lock(root):
        state = core.changed_paths(root)
        dirty = state["knowledge"]
        _require_clean_notes(root)
        if not pending_migrations(root) and _kb_toml_version(root) == _want() and applied not in state["tooling"]:
            return []
        toml_edits = "kb.toml" in dirty
        ids = _apply(root, pending_migrations(root))
        _bump_kb_toml(root)
        paths = ["kb.toml"] + ([applied] if os.path.isfile(os.path.join(root, applied)) else [])
        subject = f"chore(schema): schema {_want()}" + (f" ({', '.join(ids)})" if ids else "")
        body = "\nkb.toml also carried uncommitted edits; they are in this commit.\n" if toml_edits else ""
        core._commit_paths(root, paths, subject + "\n" + body)
        print(f"committed {subject}")
        core.push_main(root, quiet=True)
    if [p for p in core.changed_paths(root)["knowledge"] if p not in ignore and not is_index_path(p)]:
        core.commit_op("refine", f"schema-{_want().replace('.', '-')}", f"migrate notes to schema {_want()}", root=root)
    return ids


def run(root, branch, check=False, dry_run=False):
    """Apply pending migrations in order. Returns the ids applied (or pending, with check). `dry_run` does the full
    preflight (see `check_before_writing`) and writes nothing. Every real run does the same preflight first."""
    if check:
        return pending_migrations(root)
    own = own_repo(root)
    if own and branch == "main":
        _require_clean_notes(root)                  # cheap refusals first
    elif pending_migrations(root) and not branch.startswith("infra/"):
        if own:
            raise RuntimeError(f"a kb repo migrates on its main (current: {branch or 'detached'})")
        raise RuntimeError("the engine, and a kb tracked by it (examples/demo), migrate inside a schema PR (infra/* branch)")
    if dry_run or pending_migrations(root) or (own and _kb_toml_version(root) != _want()):
        ids = check_before_writing(root, dry_run, bump=own and branch == "main")
        if dry_run:
            return ids
    if own and branch == "main":
        return _migrate_own_repo(root)
    pending = pending_migrations(root)
    if not pending:
        return pending
    if not branch.startswith("infra/"):
        if own:
            raise RuntimeError(f"a kb repo migrates on its main (current: {branch or 'detached'})")
        raise RuntimeError("the engine, and a kb tracked by it (examples/demo), migrate inside a schema PR (infra/* branch)")
    return _apply(root, pending)
