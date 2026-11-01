"""`distill hooks install --kb <id|path>`: wire a knowledge base to the kit's hooks.

Two kinds of hook, both from `kits/base/hooks/` (package data, so this works from a wheel as well as a checkout):

  git hooks         `core.hooksPath` of the kb repo (local config, nothing committed) -> the kit's hooks folder
                    (`kbconfig.hooks_path_for`): pre-commit, commit-msg, pre-push, each one `distill hook <name>`
  Claude Code hooks `.claude/settings.json` + `.claude/hooks/{kb-guard,kb-git-guard}.sh` in the kb, each one
                    `distill hook guard|git-guard`

Every hook calls `distill` and nothing else: no engine folder, no PYTHONPATH. They fail closed when `distill` is
missing (exit 2). Git silently skips a hook that is not executable, which would be a fail-open path, so a non-executable
git hook makes the install exit 1 instead of reporting success.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from kb_distillery import kbconfig
from kb_distillery.config import resources

HOOKS_DIR = "kits/base/hooks"
GIT_HOOKS = ("pre-commit", "commit-msg", "pre-push")
CLAUDE_HOOKS = ("kb-guard.sh", "kb-git-guard.sh")
SETTINGS = "claude-settings.json"


def _executable(path: str) -> bool:
    return os.path.isfile(path) and bool(os.stat(path).st_mode & stat.S_IXUSR)


def _sync_file(src: str, dest: str, mode: int | None = None) -> str | None:
    """Copy `src` over `dest` unless it already has those bytes (and mode) -> "added", "updated" or None (unchanged)."""
    same = os.path.isfile(dest) and Path(src).read_bytes() == Path(dest).read_bytes()
    state = None if same else ("updated" if os.path.isfile(dest) else "added")
    if not same:
        shutil.copyfile(src, dest)
    if mode is not None and (not os.path.isfile(dest) or stat.S_IMODE(os.stat(dest).st_mode) != mode):
        os.chmod(dest, mode)
        state = state or "updated"
    return state


def install_claude(kb_root: str, report: list[str] | None = None) -> int:
    """The Claude Code half: `.claude/hooks/*.sh` and `.claude/settings.json`. Idempotent. `report` collects one line per
    file that was added or updated (nothing for a file that already matched)."""
    report = [] if report is None else report
    kit = str(resources.resource(HOOKS_DIR))
    missing = [n for n in (*GIT_HOOKS, *CLAUDE_HOOKS, SETTINGS) if not os.path.isfile(os.path.join(kit, n))]
    if missing:
        print(f"error: the kit hooks are incomplete in {kit}: missing {', '.join(missing)}", file=sys.stderr)
        return 1
    dest = os.path.join(kb_root, ".claude", "hooks")
    os.makedirs(dest, exist_ok=True)
    for name in CLAUDE_HOOKS:
        state = _sync_file(os.path.join(kit, name), os.path.join(dest, name), 0o755)
        if state:
            report.append(f"{state} .claude/hooks/{name}")
    settings, wanted = os.path.join(kb_root, ".claude", "settings.json"), os.path.join(kit, SETTINGS)
    if os.path.isfile(settings) and Path(settings).read_bytes() != Path(wanted).read_bytes():
        print(f"note: replacing {settings} (previous copy: settings.json.bak)")
        shutil.copyfile(settings, settings + ".bak")
        report.append("updated .claude/settings.json (previous copy: .claude/settings.json.bak)")
    elif not os.path.isfile(settings):
        report.append("added .claude/settings.json")
    shutil.copyfile(wanted, settings)
    print(f"claude hooks: {settings} (guard + git guard run `distill hook guard|git-guard`)")
    return 0


def install_git(kb_root: str, report: list[str] | None = None) -> int:
    """The git half: `core.hooksPath` of the kb repo -> the kit's hooks. Needs the kb at its final place (the path is
    relative to it). A kb that is not a git repository is told so and counts as done."""
    report = [] if report is None else report
    if not os.path.exists(os.path.join(kb_root, ".git")):
        print(f"git hooks: {kb_root} is not a git repository - only the Claude Code hooks were installed")
        return 0
    hooks_path = kbconfig.hooks_path_for(kb_root)
    old = subprocess.run(["git", "-C", kb_root, "config", "--local", "--get", "core.hooksPath"], capture_output=True, text=True).stdout.strip()
    proc = subprocess.run(["git", "-C", kb_root, "config", "core.hooksPath", hooks_path], capture_output=True, text=True)
    if proc.returncode:
        print(f"error: git config core.hooksPath failed: {proc.stderr.strip()}", file=sys.stderr)
        return 1
    if old != hooks_path:
        report.append(f"core.hooksPath {old or '(unset)'} -> {hooks_path}")
    print(f"git hooks: {kb_root} core.hooksPath -> {hooks_path}")
    resolved = hooks_path if os.path.isabs(hooks_path) else os.path.normpath(os.path.join(kb_root, hooks_path))
    dead = [n for n in GIT_HOOKS if not _executable(os.path.join(resolved, n))]
    if dead:
        print(f"error: git would skip these hooks (missing or not executable) in {resolved}: {', '.join(dead)}", file=sys.stderr)
        return 1
    if shutil.which("distill") is None:
        print("warning: `distill` is not on PATH here; the hooks refuse every commit and guarded edit (fail closed) "
              "until it is - install kb-distillery or add its bin folder to PATH", file=sys.stderr)
    return 0


def install(kb_root: str, report: list[str] | None = None) -> int:
    rc = install_claude(kb_root, report)
    return rc or install_git(kb_root, report)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["-h"], ["--help"]):
        print("usage: distill hooks install --kb <id|path>\n\n" + __doc__)
        return 0
    try:
        cfg = kbconfig.current()
    except kbconfig.KbConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if cfg is None:
        print("error: no knowledge base selected - pass --kb <id|path> or set KB (`distill kb list`)", file=sys.stderr)
        return 1
    return install(cfg.root)


if __name__ == "__main__":
    raise SystemExit(main())
