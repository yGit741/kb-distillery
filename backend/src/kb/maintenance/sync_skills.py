#!/usr/bin/env python3
"""Copy skills/ → .cursor/skills/ and .claude/skills/ (no symlinks)."""
import os
import shutil
import sys

from kb.paths import vault_root
ROOT = vault_root()
SRC = os.path.join(ROOT, "skills")
DSTS = [os.path.join(ROOT, ".cursor", "skills"), os.path.join(ROOT, ".claude", "skills")]

DEPRECATED = {"thesis-ingest"}


def sync_to(dst):
    os.makedirs(dst, exist_ok=True)
    copied = 0
    for name in sorted(os.listdir(SRC)):
        src_path = os.path.join(SRC, name)
        if not os.path.isdir(src_path) and name != "README.md":
            continue
        if name in DEPRECATED:
            continue
        dst_path = os.path.join(dst, name)
        if os.path.isdir(src_path):
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)
            copied += 1
            print(f"  {name}/")
    # README at skills root for discoverability
    readme = os.path.join(SRC, "README.md")
    if os.path.isfile(readme):
        shutil.copy2(readme, os.path.join(dst, "README.md"))
    # Remove deprecated skills from mirror
    for dep in DEPRECATED:
        dep_path = os.path.join(dst, dep)
        if os.path.isdir(dep_path):
            shutil.rmtree(dep_path)
            print(f"  removed deprecated {dep}/")
    return copied


def main():
    from kb.lint.lint_skills import main as lint_main

    if lint_main() != 0:
        print("sync-skills aborted: lint-skills failed")
        return 1

    if not os.path.isdir(SRC):
        print(f"missing {SRC}")
        return 1

    for dst in DSTS:
        copied = sync_to(dst)
        print(f"synced {copied} skill(s) → {os.path.relpath(dst, ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
