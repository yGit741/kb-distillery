"""distill kb import: turn an OKF bundle (a folder or a .zip) into a NEW knowledge base.

    distill kb import <bundle.zip|folder|git-url[#ref]> [--kit KIT] [--id KB-ID] [--dir PARENT] [--dry-run]

The bundle root is `wiki/` (see `config.layout`). The source may be that folder, a folder holding `wiki/`, or a folder whose
single top-level entry is one of those (what zipping a folder produces). The bundle is checked with `lint.okf_check` BEFORE
anything is written; errors are printed and nothing is created. The kb is made by `init_kb.create` (same kit default as
`distill init`), the bundle is copied into its `wiki/`, the engine's own lint regenerates `wiki/index.md` and
`meta/corpus.tsv`, and one `kb(import)` commit records it. If anything after the kb exists fails, the new folder is removed.
A git URL is shallow-cloned once into a temp dir (the clone's .git is dropped; `[import]` in kb.toml records source, ref, commit). A zip is extracted into a temp dir with the zip-slip checks of `_safe_extract` (no absolute or `..` entries, no symlinks).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field

from kb_distillery import init_kb
from kb_distillery.config import kb as kbconfig
from kb_distillery.config.layout import WIKI_DIR
from kb_distillery.lint import okf_check

IGNORED = {".DS_Store", "__MACOSX", ".git"}


class BundleError(init_kb.InitError):
    """Nothing was created; the message says why."""



def _safe_extract(archive: str, dest: str) -> None:
    """Extract a zip into the empty folder `dest`, rejecting absolute paths, `..` entries and symlinks."""
    root = os.path.realpath(dest)
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as e:
        raise BundleError(f"{archive} is not a readable zip: {e}") from None
    with zf:
        for info in zf.infolist():
            name = info.filename
            parts = name.replace("\\", "/").split("/")
            if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name) or ".." in parts:
                raise BundleError(f"unsafe path in zip: {name!r} (absolute or contains ..)")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise BundleError(f"unsafe entry in zip: {name!r} is a symlink")
            if not os.path.realpath(os.path.join(root, *parts)).startswith(root + os.sep):
                raise BundleError(f"unsafe path in zip: {name!r} leaves the extraction folder")
        zf.extractall(root)


def _entries(folder: str) -> list[str]:
    return sorted(n for n in os.listdir(folder) if n not in IGNORED)


def find_bundle_root(folder: str) -> str:
    """The OKF bundle root inside `folder`: a `wiki/` in it, a single top-level folder (descend), else `folder` itself."""
    for _ in range(3):
        wiki = os.path.join(folder, WIKI_DIR)
        if os.path.isdir(wiki):
            return wiki
        names = _entries(folder)
        if len(names) == 1 and os.path.isdir(os.path.join(folder, names[0])) and not os.path.islink(os.path.join(folder, names[0])):
            folder = os.path.join(folder, names[0])
            continue
        break
    return folder


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")


def default_id(src: str) -> str:
    """A kb id from the source name (zip stem or folder name; `wiki` takes its parent's name)."""
    path = os.path.realpath(os.path.expanduser(src))
    base = os.path.basename(path)
    if os.path.isfile(path):
        base = os.path.splitext(base)[0]
    elif base == WIKI_DIR:
        base = os.path.basename(os.path.dirname(path))
    slug = _slug(base)
    return slug if slug and slug[0].isalnum() else "imported-kb"


@dataclass
class Report:
    """What a dry run found; nothing was written."""
    id: str
    source: str
    pages: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ref: str = ""
    commit: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors and self.pages > 0


def is_git_source(src: str) -> bool:
    return bool(re.match(r"^(https?://|ssh://|git@)", src))


def _clone(url: str, ref: str, dest: str) -> str:
    """Shallow clone `url` (at `ref`, if any) into the empty `dest` with the user's own git credentials -> HEAD sha."""
    cmd = ["git", "clone", "--quiet", "--depth", "1", *(["--branch", ref] if ref else []), "--", url, dest]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if proc.returncode != 0:
        raise BundleError(f"could not clone {url}: {(proc.stderr or proc.stdout).strip()}")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True, text=True).stdout.strip()


def _findings(bundle: str, stage: str) -> tuple[int, list[str], list[str]]:
    """okf-check `bundle` as the `wiki/` of a throwaway root -> (page count, errors, warnings). Errors block an import."""
    root = os.path.join(stage, "check")
    shutil.copytree(bundle, os.path.join(root, WIKI_DIR), symlinks=True, ignore=shutil.ignore_patterns(*IGNORED))
    for base, dirs, files in os.walk(os.path.join(root, WIKI_DIR)):
        for n in dirs + files:
            if os.path.islink(os.path.join(base, n)):
                return 0, [f"the bundle contains a symlink: {os.path.relpath(os.path.join(base, n), root)}"], []
    findings, count = okf_check.check(root)
    errors = [f"{rel}: [{rule}] {msg}" for rel, items in sorted(findings.items()) for rule, msg in items]
    if not count and not errors:
        errors.append("the bundle has no pages (no .md files besides index.md / log.md)")
    return count, errors, []


@contextlib.contextmanager
def _open(source: str, stage: str):
    """Resolve a folder, .zip or git URL[#ref] to its bundle folder -> (bundle, source label, ref, commit)."""
    ref = commit = ""
    if is_git_source(source):
        url, _, ref = source.partition("#")
        folder = os.path.join(stage, "clone")
        commit = _clone(url, ref, folder)
        label = url
    else:
        label = os.path.realpath(os.path.expanduser(source))
        if not os.path.exists(label):
            raise BundleError(f"{label} does not exist")
        if os.path.isfile(label):
            folder = os.path.join(stage, "unzipped")
            os.makedirs(folder)
            _safe_extract(label, folder)
        elif os.path.isdir(label):
            folder = label
        else:
            raise BundleError(f"{label} is neither a folder nor a .zip file")
    yield find_bundle_root(folder), label, ref, commit


def _guess_id(source: str) -> str:
    if is_git_source(source):
        base = source.partition("#")[0].rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
        return default_id(re.sub(r"\.git$", "", base) or "imported-kb")
    return default_id(source)


def _id_taken(kb_id: str, parent: str | None) -> bool:
    parent = parent or kbconfig.bases_dir()
    return kb_id in kbconfig.discover() or os.path.lexists(os.path.join(os.path.expanduser(parent), kb_id))


def validate_bundle(source: str, kb_id: str | None = None, parent: str | None = None) -> Report:
    """Dry run: check the bundle at `source` (folder, .zip or git URL[#ref]) and write nothing -> `Report`
    (suggested id, page count, errors that block an import, warnings). A bad source raises `BundleError`."""
    kb_id = kb_id or _guess_id(source)
    with tempfile.TemporaryDirectory(prefix="kb-import-") as stage, _open(source, stage) as (bundle, label, ref, commit):
        count, errors, warnings = _findings(bundle, stage)
    try:
        init_kb.validate_id(kb_id)
    except init_kb.InitError as e:
        errors.append(str(e))
    else:
        if _id_taken(kb_id, parent):
            errors.append(f"a knowledge base {kb_id!r} already exists: pick another --id")
    return Report(kb_id, label, count, errors, warnings, ref, commit)


def _record_source(target: str, rep: Report) -> None:
    """Append `[import]` (where the pages came from) to the new kb.toml."""
    def q(v):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = ["", "[import]", f"source = {q(rep.source)}"]
    if rep.ref:
        lines.append(f"ref = {q(rep.ref)}")
    if rep.commit:
        lines.append(f"commit = {q(rep.commit)}")
    lines.append(f"imported_at = {q(now)}")
    with open(os.path.join(target, kbconfig.CONFIG_NAME), "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _build_views(target: str) -> None:
    """The graph and page reader read the wiki files directly; lint writes the index/corpus they list. Nothing else to build."""
    _lint(target)


def _lint(root: str) -> None:
    env = dict(os.environ, KB_ROOT=root)
    env.pop("KB", None)
    proc = subprocess.run([sys.executable, "-m", "kb_distillery.lint.lint"], cwd=root, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout or proc.stderr or "").splitlines()[-8:])
        raise BundleError(f"lint failed on the imported pages:\n{tail}")


def import_bundle(src: str, kit: str | None = None, kb_id: str | None = None, parent: str | None = None,
                  name: str | None = None) -> str:
    """Import the OKF bundle at `src` (folder, .zip or git URL[#ref]) as a NEW kb -> the new kb's path.

    A git source is a one-time shallow copy: the clone's .git is dropped and the kb gets its own history; `[import]` in
    kb.toml records source, ref, commit and time. okf_check errors raise `BundleError` (an `init_kb.InitError`) with nothing
    written; so does an id that is taken or a kit that is unknown. `parent` defaults to the bases dir (`~/knowledge`)."""
    kb_id = kb_id or _guess_id(src)
    init_kb.validate_id(kb_id)
    parent = parent or kbconfig.bases_dir()
    with tempfile.TemporaryDirectory(prefix="kb-import-") as stage, _open(src, stage) as (bundle, label, ref, commit):
        count, errors, warnings = _findings(bundle, stage)
        rep = Report(kb_id, label, count, errors, warnings, ref, commit)
        if _id_taken(kb_id, parent):
            raise BundleError(f"a knowledge base {kb_id!r} already exists: pick another --id")
        if errors:
            raise BundleError(f"the bundle is not valid OKF ({len(errors)} finding(s)); nothing was written:\n"
                              + "\n".join("  " + e for e in errors))
        target = init_kb.create(kb_id, name or kb_id.replace("-", " ").capitalize(), kit or init_kb.DEFAULT_KIT, parent)
        try:
            shutil.copytree(bundle, os.path.join(target, WIKI_DIR), dirs_exist_ok=True, symlinks=False,
                            ignore=shutil.ignore_patterns(*IGNORED))
            _record_source(target, rep)
            _build_views(target)
            from kb_distillery.git import commit_policy as cp
            from kb_distillery.ops.core import OpsError, _commit_paths, _message
            with init_kb._identity_if_missing():
                try:
                    sha = _commit_paths(target, [WIKI_DIR, "meta", kbconfig.CONFIG_NAME],
                                        _message("import", f"{count} page(s) from {os.path.basename(label.rstrip('/'))}",
                                                 cp.next_version(target), kb_id))
                except OpsError as e:
                    raise BundleError(f"could not commit the import: {e}") from None
            if not sha:
                raise BundleError("nothing to commit after copying the bundle")
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="distill kb import", description=__doc__.split("\n\n")[0])
    ap.add_argument("source", help="an OKF bundle: a folder, a .zip or a git URL (https:// or git@, optional #ref)")
    ap.add_argument("--kit", help=f"ontology kit for the new kb (default {init_kb.DEFAULT_KIT})")
    ap.add_argument("--id", dest="kb_id", help="id of the new kb (default: derived from the folder or zip name)")
    ap.add_argument("--dir", help="parent folder for the new kb (default: the bases dir, ~/knowledge)")
    ap.add_argument("--dry-run", action="store_true", help="validate only: print id, page count, errors, warnings; write nothing")
    args = ap.parse_args(argv)
    if args.dry_run:
        try:
            rep = validate_bundle(args.source, args.kb_id, args.dir)
        except init_kb.InitError as e:
            print(f"distill kb import: {e}", file=sys.stderr)
            return 1
        print(f"would import {rep.pages} page(s) from {rep.source} as {rep.id!r}")
        for w in rep.warnings:
            print(f"warning: {w}")
        for e in rep.errors:
            print(f"error: {e}", file=sys.stderr)
        return 0 if rep.ok else 1
    try:
        target = import_bundle(args.source, args.kit, args.kb_id, args.dir)
    except init_kb.InitError as e:
        print(f"distill kb import: {e}", file=sys.stderr)
        return 1
    print(f"imported into {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
