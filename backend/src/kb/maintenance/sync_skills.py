#!/usr/bin/env python3
"""Make `.claude/skills` a symlink to `skills/` (one source, no copies).

    python3 -m kb.maintenance.sync_skills           lint, then create/repair the links
    python3 -m kb.maintenance.sync_skills --check   verify only (exit 1 if a link is wrong)

Each link is relative (`../skills`), so it survives moving the vault and works in worktrees.
"""
import os
import shutil
import sys

from kb.paths import CHECKOUT_ROOT, vault_root

ROOT = CHECKOUT_ROOT          # skills are code: they live with the explorer
SRC = os.path.join(ROOT, "skills")
LINK_TARGET = os.path.join("..", "skills")
LINKS = [os.path.join(ROOT, ".claude", "skills")]

DEPRECATED = {"thesis-ingest"}


def link_ok(path: str) -> bool:
    return os.path.islink(path) and os.readlink(path) == LINK_TARGET and os.path.isdir(path)


def ensure_link(path: str) -> str:
    """Create or repair one symlink; return 'ok', 'created' or 'replaced'."""
    if link_ok(path):
        return "ok"
    status = "created"
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
        status = "replaced"
    elif os.path.isdir(path):
        shutil.rmtree(path)  # a stale copied mirror
        status = "replaced"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    os.symlink(LINK_TARGET, path)
    return status


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    check = "--check" in args

    from kb.lint.lint_skills import main as lint_main

    if lint_main([]) != 0:
        print("sync-skills aborted: lint-skills failed")
        return 1

    if not os.path.isdir(SRC):
        print(f"missing {SRC}")
        return 1

    bad = 0
    for link in LINKS:
        rel = os.path.relpath(link, ROOT)
        if check:
            if link_ok(link):
                print(f"ok {rel} -> {LINK_TARGET}")
            else:
                print(f"ERROR {rel} is not a symlink to {LINK_TARGET} (run pixi run sync-skills)")
                bad += 1
        else:
            print(f"{ensure_link(link)} {rel} -> {LINK_TARGET}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
