#!/usr/bin/env python3
"""Move the vault tooling from `meta/` into the `backend/` app layout (package `kb`), scripted.

    python tools/restructure/restructure.py --dry-run     # plan + counts, writes nothing
    python tools/restructure/restructure.py               # perform the whole move on a clean checkout
    python tools/restructure/restructure.py --verify      # check the result (read-only); exit 1 on findings

Idempotent: a second run finds nothing left to move. Safe to re-run after `main` gained new files under
`meta/` (they are routed by tools/restructure/layout.py; anything no rule claims is reported, not guessed).
Plain filesystem moves are used (the git guard blocks raw `git mv`); git detects the renames at commit
time because file contents change only in import/path lines. Stdlib only.
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import codemod  # noqa: E402
import layout  # noqa: E402
import patches  # noqa: E402
import scaffold  # noqa: E402
import textrules  # noqa: E402
from layout import PKG, TESTS  # noqa: E402

TEXT_EXT = {".py", ".md", ".sh", ".toml", ".json", ".jsonc", ".plist", ".yml", ".yaml", ".html", ".js", ".css",
            ".mjs", ".tsv", ".txt", ".mdc", ""}
# importable only on paper in the old layout too (imports names schema never had); not a regression
KNOWN_BROKEN = ("kb.distill.zones",)
SKIP_DIRS = {"__pycache__", ".git", ".pixi", "node_modules", ".cache"}


class Report:
    def __init__(self):
        self.moved = []
        self.skipped = []          # (path, reason)
        self.unrouted = []         # files no rule claims
        self.manual = []           # (path, note)
        self.counts = {"imports": 0, "syspath": 0, "rootdefs": 0, "textrules": 0, "patches": 0}
        self.rewritten = set()
        self.patch_misses = []

    def show(self, verbose=False):
        print(f"files moved:            {len(self.moved)}")
        print(f"files rewritten:        {len(self.rewritten)}")
        print(f"import statements:      {self.counts['imports']}")
        print(f"sys.path hacks removed: {self.counts['syspath']}")
        print(f"root definitions:       {self.counts['rootdefs']}")
        print(f"text-rule replacements: {self.counts['textrules']}")
        print(f"patch substitutions:    {self.counts['patches']}")
        if self.skipped:
            print(f"\nskipped ({len(self.skipped)}):")
            for p, why in self.skipped:
                print(f"  {p}: {why}")
        if self.unrouted:
            print(f"\nUNROUTED ({len(self.unrouted)}) — no rule claims these; decide and add to layout.py:")
            for p in self.unrouted:
                print(f"  {p}")
        if self.patch_misses:
            print(f"\nPATCH MISSES ({len(self.patch_misses)}) — pattern not found (main changed it?):")
            for p, old in self.patch_misses:
                print(f"  {p}: {old[:90]!r}")
        if self.manual:
            print(f"\nMANUAL ({len(self.manual)}):")
            for p, note in self.manual:
                print(f"  {p}: {note}")


# ----------------------------------------------------------------------------------------------
def walk(root, sub):
    base = os.path.join(root, sub)
    for dp, dns, fns in os.walk(base):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
        rel = os.path.relpath(dp, root)
        # runtime state: meta/.ingest etc.
        if any(part.startswith(".") for part in rel.split(os.sep) if part not in (".",)):
            dns[:] = []
            continue
        for fn in sorted(fns):
            if fn.endswith(".pyc") or fn == ".DS_Store":
                continue
            yield os.path.join(rel, fn).replace(os.sep, "/")


def route(path):
    """New repo-relative path for a file under meta/, '' to drop it, None when no rule claims it."""
    if path in layout.META_FILES_STAY:
        return path
    parts = path.split("/")
    assert parts[0] == "meta"
    rest = parts[1:]
    name = rest[-1]
    if len(rest) == 1:
        if name == "__init__.py":
            return ""                                   # the old `meta` package marker
        stem = name[:-3] if name.endswith(".py") else None
        if stem in layout.TOP_MODULES:
            return f"{PKG}/{layout.TOP_MODULES[stem]}/{name}"
        if stem and stem.startswith("test_"):
            pkg = layout.TEST_PACKAGE.get(stem[5:])
            return f"{TESTS}/{pkg}/{name}" if pkg else f"{TESTS}/{name}"
        if name == "launch.sh":
            return "tools/launch.sh"
        if name in layout.META_STAYS:
            return path
        return None
    top = rest[0]
    if top in layout.META_STAYS:
        return path
    if top == "migrations":
        return path if name in layout.MIGRATIONS_DATA_STAYS else f"{PKG}/migrations/{'/'.join(rest[1:])}"
    if top == "share" and rest[1:2] == ["worker"]:
        return "share/" + "/".join(rest[2:])
    if top in layout.WHOLE_PACKAGES:
        return f"{PKG}/{'/'.join(rest)}"
    if top == "dashboard":
        sub = rest[1:]
        if len(sub) == 1 and sub[0].endswith(".py"):
            stem = sub[0][:-3]
            if stem in layout.DASHBOARD_TO_SERVICES:
                return f"{PKG}/services/{layout.DASHBOARD_TO_SERVICES[stem]}.py"
        if sub and sub[0] == "prompts":
            return f"{PKG}/prompts/{'/'.join(sub[1:])}"
        return f"{PKG}/dashboard/{'/'.join(sub)}"
    if top == "testdata":
        return f"{TESTS}/testdata/" + "/".join(rest[1:])
    if top == "skills":
        return "skills/" + "/".join(rest[1:])
    if top == "githooks":
        return "tools/githooks/" + "/".join(rest[1:])
    if top == "launchd":
        return "tools/launchd/" + "/".join(rest[1:])
    if top == "tests":
        sub = rest[1:]
        if sub == ["__init__.py"]:
            return f"{TESTS}/__init__.py"
        return f"{TESTS}/{'/'.join(sub)}"
    return None


def old_depth(path):
    """Directories below meta/ the file sat in."""
    return len(path.split("/")) - 2


def dotted_pkg_old(path):
    parts = path.split("/")[1:-1]
    return ".".join(parts) if parts else None


def dotted_pkg_new(newpath):
    if not newpath.startswith(PKG + "/"):
        return None
    parts = newpath[len(PKG) + 1:].split("/")[:-1]
    return ".".join(["kb"] + parts)


def is_text(path):
    return os.path.splitext(path)[1] in TEXT_EXT


# ----------------------------------------------------------------------------------------------
def transform_py(text, oldpath, newpath, rep, siblings=()):
    notes = []
    depth = old_depth(oldpath) if oldpath else None
    if depth is not None:
        text, n = codemod.rewrite_root_defs(text, depth)
        rep.counts["rootdefs"] += sum(1 for x in n if x.startswith("root def"))
        notes += [x for x in n if x.startswith("MANUAL")]
    text = codemod.simplify_root(text)
    text, n = codemod.remove_sys_path_hacks(text, strict=not (newpath or "").startswith(TESTS + "/"))
    rep.counts["syspath"] += len(n)
    own_old = dotted_pkg_old(oldpath) if oldpath else None
    own_new = dotted_pkg_new(newpath) if newpath else None
    text, n = codemod.rewrite_imports(text, own_old, own_new, siblings)
    for x in n:
        if x.startswith("COUNT:imports:"):
            rep.counts["imports"] += int(x.rsplit(":", 1)[1])
    notes += [x for x in n if not x.startswith("COUNT:")]
    text = codemod.prune_paths_imports(text)
    return text, notes


def transform(text, oldpath, newpath, rep, siblings=()):
    """Full pipeline for one file's text. oldpath may be None (file did not move)."""
    notes = []
    if newpath.endswith(".py"):
        text, notes = transform_py(text, oldpath, newpath, rep, siblings)
    text, k = textrules.apply_rules(text)
    rep.counts["textrules"] += k
    text, k, misses = patches.apply(newpath, text)
    rep.counts["patches"] += k
    rep.patch_misses += [(newpath, m) for m in misses]
    return text, notes


# ----------------------------------------------------------------------------------------------
def collect_plan(root, rep):
    plan = []
    for p in walk(root, "meta"):
        dst = route(p)
        if dst is None:
            rep.unrouted.append(p)
        elif dst == "":
            plan.append((p, None))
        elif dst != p:
            plan.append((p, dst))
    return plan


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text, mode_from=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    if mode_from and os.path.exists(mode_from):
        shutil.copymode(mode_from, path)


def prep(root, dry):
    """Make the new top-level folders legal for the tooling lane BEFORE the move (so `ship commit` stages the
    script and everything that follows): only the schema's ROOT_DIRS / TOOLING_PATHS edit, in place."""
    rep = Report()
    path = os.path.join(root, "meta", "schema.py")
    if not os.path.isfile(path):
        path = os.path.join(root, PKG, "core", "schema.py")
    text = read(path)
    new, k, misses = patches.apply(f"{PKG}/core/schema.py", text)
    rep.counts["patches"] += k
    rep.patch_misses += [(path, m) for m in misses]
    if new != text and not dry:
        write(path, new, mode_from=path)
    return rep


def run(root, dry, phase="all"):
    if phase == "prep":
        return prep(root, dry)
    rep = Report()
    plan = collect_plan(root, rep) if phase in ("all", "move") else []

    # 1. move + transform every routed file
    dirs = {}
    for _s, d in plan:
        if d and d.startswith(TESTS + "/") and d.endswith(".py"):
            dirs.setdefault(os.path.dirname(d), set()).add(os.path.basename(d)[:-3])
    for src, dst in plan:
        sp = os.path.join(root, src)
        if dst is None:
            rep.moved.append((src, "(dropped)"))
            if not dry:
                os.remove(sp)
            continue
        dp = os.path.join(root, dst)
        if os.path.exists(dp):
            rep.skipped.append((src, f"destination {dst} exists — source wins, destination overwritten"))
        if is_text(src):
            try:
                text = read(sp)
            except UnicodeDecodeError:
                text = None
        else:
            text = None
        if text is not None:
            new, notes = transform(text, src, dst, rep, dirs.get(os.path.dirname(dst), ()))
            for n in notes:
                rep.manual.append((dst, n))
            rep.rewritten.add(dst)
            if not dry:
                write(dp, new, mode_from=sp)
                os.remove(sp)
        else:
            if not dry:
                os.makedirs(os.path.dirname(dp), exist_ok=True)
                shutil.move(sp, dp)
        rep.moved.append((src, dst))

    # 2. scaffolding: packages, paths.py, pyproject, conftest
    if phase in ("all", "move"):
        scaffold.create(root, rep, dry)

    # 3. files that did not move but reference moved things (docs, configs, hooks)
    for rel in patches.STATIC_TEXT_FILES(root, phase):
        fp = os.path.join(root, rel)
        if not os.path.isfile(fp) or not is_text(rel):
            continue
        text = read(fp)
        new, notes = transform(text, None, rel, rep)
        for n in notes:
            rep.manual.append((rel, n))
        if new != text:
            rep.rewritten.add(rel)
            if not dry:
                write(fp, new, mode_from=fp)

    # 4. already-moved files that main touched since (idempotent re-run): re-apply patches to the new tree
    for rel in (patches.PATCHED_NEW_FILES() if phase in ("all", "move") else []):
        fp = os.path.join(root, rel)
        if not os.path.isfile(fp) or rel in rep.rewritten:
            continue
        text = read(fp)
        new, k, misses = patches.apply(rel, text)
        rep.counts["patches"] += k
        rep.patch_misses += [(rel, m) for m in misses if m]
        if new != text:
            rep.rewritten.add(rel)
            if not dry:
                write(fp, new, mode_from=fp)

    # 5. clean up the emptied old tree (pycache, empty dirs)
    if not dry and phase in ("all", "move"):
        cleanup(root)
        sync_skill_mirrors(root, rep)
    return rep


def sync_skill_mirrors(root, rep):
    """Regenerate .claude/skills and .cursor/skills from skills/ (their SKILL.md carry the rewritten commands)."""
    env = dict(os.environ, PYTHONPATH=os.path.join(root, "backend", "src"), PYTHONDONTWRITEBYTECODE="1")
    env.pop("KB_ROOT", None)
    cp = subprocess.run([sys.executable, "-m", "kb.maintenance.sync_skills"], cwd=root, env=env,
                        capture_output=True, text=True)
    if cp.returncode != 0:
        rep.manual.append((".claude/skills", "sync_skills failed — fix skills/ then run `pixi run sync-skills`:\n"
                           + (cp.stdout + cp.stderr).strip()[-1500:]))


def cleanup(root):
    meta = os.path.join(root, "meta")
    for dp, dns, fns in os.walk(meta, topdown=False):
        rel = os.path.relpath(dp, meta)
        if any(p.startswith(".") for p in rel.split(os.sep) if p != "."):
            continue
        if os.path.basename(dp) == "__pycache__":
            shutil.rmtree(dp, ignore_errors=True)
            continue
        try:
            if not os.listdir(dp) and dp != meta:
                os.rmdir(dp)
        except OSError:
            pass


# ----------------------------------------------------------------------------------------------
def verify(root):
    problems = []
    for p in walk(root, "meta"):
        if route(p) not in (p,):
            problems.append(f"still under meta/: {p}")
    for sub in ("backend", "tools", "share", "skills"):
        for dp, dns, fns in os.walk(os.path.join(root, sub)):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                if not fn.endswith(".py"):
                    continue
                fp = os.path.join(dp, fn)
                rel = os.path.relpath(fp, root)
                text = read(fp)
                if rel.startswith("backend") and "sys.path.insert" in text:
                    if rel not in patches.SYS_PATH_ALLOWED:
                        problems.append(f"sys.path.insert left in {rel}")
    env = dict(os.environ, PYTHONPATH=os.path.join(root, "backend", "src"), PYTHONDONTWRITEBYTECODE="1")
    mods = []
    base = os.path.join(root, "backend", "src")
    for dp, dns, fns in os.walk(os.path.join(base, "kb")):
        dns[:] = [d for d in dns if d != "__pycache__"]
        for fn in fns:
            if fn.endswith(".py") and not fn[:4].isdigit():
                rel = os.path.relpath(os.path.join(dp, fn), base)[:-3].replace(os.sep, ".")
                mods.append(rel[:-9] if rel.endswith(".__init__") else rel)
    code = ("import importlib,sys\nsys.path.insert(0, %r)\nbad=[]\nfor m in sys.argv[1:]:\n  if m.endswith('.__main__'): continue\n"
            "  try: importlib.import_module(m)\n  except Exception as e: bad.append((m, repr(e)[:160]))\n"
            "[print('IMPORT FAIL', m, e) for m, e in bad]\nraise SystemExit(1 if bad else 0)\n") % base
    cp = subprocess.run([sys.executable, "-c", code, *sorted(mods)], env=env, cwd=root,
                        capture_output=True, text=True)
    if cp.returncode != 0:
        problems += [l for l in (cp.stdout + cp.stderr).strip().splitlines()
                     if not any(k in l for k in KNOWN_BROKEN)]
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.path.abspath(os.path.join(HERE, "..", "..")))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--phase", choices=("all", "prep", "move", "refs", "docs"), default="all",
                    help="run one stage so each lands as its own commit: prep (schema accepts the new folders), "
                         "move (files, imports, pixi tasks), "
                         "refs (agent/CI/hook configs), docs (markdown)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.verify:
        problems = verify(root)
        for p in problems:
            print("VERIFY:", p)
        print("verify:", "FAILED" if problems else "ok")
        return 1 if problems else 0
    rep = run(root, args.dry_run, args.phase)
    rep.show()
    if args.dry_run:
        print("\n(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
