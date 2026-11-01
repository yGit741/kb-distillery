"""Gate result reuse for `ship`: a gate that already passed on exactly this content is not run again.

The key is (gate, scope, tree sha, resolved KB, extra). The tree sha is built from a throwaway index
(`git add -A` + `git write-tree`), so it covers tracked, modified and untracked-but-not-ignored files, is the same
whether a change is uncommitted (`ship commit`) or committed (`ship pr`), and never touches the real index or HEAD.
Generated files (lint rewrites them on every run) and `.cache/` are left out of it.

Records are small JSON files under `<root>/.cache/ship-gates/reuse/`. Only a real pass is ever recorded (the caller
decides that); a record is looked up by exact key match only.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

REUSE_DIR = os.path.join(".cache", "ship-gates", "reuse")
KEEP_RECORDS = 300
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# paths that never belong in the fingerprint besides the caller's generated files
ALWAYS_EXCLUDED = (".cache",)


def tree_sha(root, exclude=()):
    """Tree sha of the work tree at `root` minus `exclude` and `.cache`, or None when it cannot be computed."""
    tmp = tempfile.mkdtemp(prefix="ship-index-")
    env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"))
    try:
        def git(*args):
            return subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True, check=False)
        if git("add", "-A").returncode != 0:
            return None
        drop = [*ALWAYS_EXCLUDED, *exclude]
        if git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", *drop).returncode != 0:
            return None
        cp = git("write-tree")
        sha = (cp.stdout or "").strip() if cp.returncode == 0 else ""
        return sha if SHA_RE.match(sha) else None
    except OSError:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def make_key(name, scope, sha, kb, extra=""):
    # `day`: lint and flags-check fail on an expired flag, so a pass is good for the day it was made
    return {"gate": name, "scope": scope, "tree": sha, "kb": kb, "extra": extra, "day": time.strftime("%Y-%m-%d")}


def _file(root, key):
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:24]
    return os.path.join(root, REUSE_DIR, f"{key['gate']}-{key['scope']}-{key['tree'][:7]}-{digest}.json")


def hit(root, key):
    """True when a record with exactly this key exists under `root`."""
    try:
        with open(_file(root, key), encoding="utf-8") as f:
            return json.load(f).get("key") == key
    except (OSError, ValueError):
        return False


def record(root, key):
    """Write the record of a real pass under `root` (never anywhere else); old records are pruned."""
    path = _file(root, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"key": key, "recorded": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)
    files = sorted((os.path.join(os.path.dirname(path), n) for n in os.listdir(os.path.dirname(path))),
                   key=os.path.getmtime)
    for old in files[:-KEEP_RECORDS]:
        try:
            os.remove(old)
        except OSError:
            pass


# ---- pytest subset selection ------------------------------------------------------------------------------------

PKG_PREFIX = "src/kb_distillery/"
CONFIG_NAMES = {"pixi.toml", "pixi.lock", "pyproject.toml", "setup.cfg", "pytest.ini", "tox.ini", "conftest.py"}


def test_subset(paths, root, ignore=lambda p: False):
    """Pytest targets for a commit-time subset run, or None when the touched paths cannot be mapped (run full).

    Targets: `tests/<pkg>` for each touched `src/kb_distillery/<pkg>/`, each changed `tests/**/test_*.py`, and always
    the top-level `tests/test_*.py` (repo-wide invariants a mirror-only selection would miss). Anything else that
    can change test outcomes (config, conftest, fixtures, a package without a mirror, skills/, meta-defaults/,
    web/, examples/ ...) returns None. Only top-level `*.md` files are free.
    """
    targets = set()
    for p in paths:
        base = os.path.basename(p)
        if p.startswith(".cache/") or ignore(p):
            continue                                         # our own logs and records; generated files
        if base in CONFIG_NAMES:
            return None
        if p.startswith(PKG_PREFIX):
            rest = p[len(PKG_PREFIX):]
            if "/" not in rest:
                return None                                  # a top-level module: no mirror, anything may use it
            mirror = f"tests/{rest.split('/', 1)[0]}"
            if not os.path.isdir(os.path.join(root, mirror)):
                return None
            targets.add(mirror)
        elif p.startswith("tests/"):
            name = os.path.basename(p)
            if not p.endswith(".py"):
                return None                                  # fixtures / test data: who reads them is unknown
            if name == "__init__.py":
                continue
            if not name.startswith("test_"):
                return None                                  # a helper module: any test may import it
            if os.path.isfile(os.path.join(root, p)):        # a deleted test file has nothing to run
                targets.add(p)
        elif "/" not in p and p.endswith(".md"):
            continue
        else:
            return None
    top = sorted(f"tests/{n}" for n in os.listdir(os.path.join(root, "tests"))
                 if n.startswith("test_") and n.endswith(".py")) if os.path.isdir(os.path.join(root, "tests")) else []
    # a dir target already covers the files under it
    files = sorted(t for t in targets if t.endswith(".py") and not any(t.startswith(d + "/") for d in targets))
    dirs = sorted(t for t in targets if not t.endswith(".py"))
    return [*dirs, *files, *top]
