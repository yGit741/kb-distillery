#!/usr/bin/env python3
"""Release helper: prepare a version bump, print the exact ship commands for the owner.

    pixi run release -- <version>           # e.g. 0.2.0 (run on an infra/ branch)
    python -m kb_distillery.git.release --notes <version>   # print that version's CHANGELOG section (release.yml uses it)

What `<version>` does: sets `version` in pyproject.toml and moves the `[Unreleased]` entries of CHANGELOG.md under a
new `## [<version>] - <date>` heading (an empty `[Unreleased]` stays in front). It writes files only, never git: it
refuses on main (a release bump lands by pull request like any change), then prints the sequence the owner runs:

    pixi run ship -- commit "chore(release): v<version>"  ->  ship -- pr  ->  ship -- merge
    pixi run ship -- tag v<version>   (a local annotated tag on main)
    git push origin v<version>        (the owner's push; it triggers .github/workflows/release.yml)

The tag is never created or pushed here: `ship -- tag` refuses a dirty or non-main tree and a tag that exists, and
pushing it is the owner's act (agents never release).

Release cadence is the owner's call (not encoded here): any newer version can be cut from `[Unreleased]` at any time.
The version in pyproject.toml, the tag (`v<version>`), the wheel, the web bundle and the image tag all match.
"""
import argparse
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
PYPROJECT_VERSION_RE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.M)
UNRELEASED = "## [Unreleased]"


class ReleaseError(Exception):
    pass


def _parse(version):
    m = VERSION_RE.match(version)
    if not m:
        raise ReleaseError(f"version {version!r} must look like 0.2.0 (no leading v)")
    return tuple(int(g) for g in m.groups())


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def current_version(root=ROOT):
    m = PYPROJECT_VERSION_RE.search(_read(os.path.join(root, "pyproject.toml")))
    if not m:
        raise ReleaseError("no version in pyproject.toml")
    return m.group(2)


def changelog_section(version, root=ROOT):
    """The body of `## [<version>]` (up to the next `## [`), stripped; ReleaseError when missing or empty."""
    _parse(version)
    text = _read(os.path.join(root, "CHANGELOG.md"))
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.M | re.S)
    body = m.group(1).strip() if m else ""
    if not body:
        raise ReleaseError(f"CHANGELOG.md has no entries under ## [{version}]")
    return body


def prepare(version, root=ROOT, branch=None, today=None):
    """Bump pyproject.toml and move [Unreleased] to [<version>] - <date>. Files only; returns the commands to run."""
    new = _parse(version)
    if branch in (None, "", "main"):
        raise ReleaseError("run this on an infra/ branch (pixi run ship -- start release-v%s --worktree): "
                           "a release bump lands by pull request, never on main" % version)
    old = current_version(root)
    if new <= _parse(old):
        raise ReleaseError(f"{version} is not newer than the current version {old}")
    cl_path = os.path.join(root, "CHANGELOG.md")
    cl = _read(cl_path)
    if re.search(rf"^## \[{re.escape(version)}\]", cl, re.M):
        raise ReleaseError(f"CHANGELOG.md already has a ## [{version}] section")
    head, sep, rest = cl.partition(UNRELEASED)
    if not sep:
        raise ReleaseError("CHANGELOG.md has no '## [Unreleased]' heading")
    body, nxt, tail = rest.partition("\n## [")
    if not body.strip():
        raise ReleaseError("## [Unreleased] is empty: nothing to release")
    stamp = (today or date.today()).isoformat()
    new_cl = f"{head}{UNRELEASED}\n\n## [{version}] - {stamp}\n\n{body.strip()}\n"
    if nxt:
        new_cl += f"\n## [{tail}"
    pp_path = os.path.join(root, "pyproject.toml")
    pp = PYPROJECT_VERSION_RE.sub(lambda m: m.group(1) + version + m.group(3), _read(pp_path), count=1)
    _write(cl_path, new_cl)
    _write(pp_path, pp)
    return commands(version)


def commands(version):
    return [
        f'pixi run ship -- commit "chore(release): v{version}"',
        "pixi run ship -- review --pass \"<summary>\"",
        f'pixi run ship -- pr --title "chore(release): v{version}"',
        "pixi run ship -- merge",
        f"pixi run ship -- tag v{version}",
        f"git push origin v{version}",
    ]


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(prog="python -m kb_distillery.git.release", description=__doc__.split("\n\n")[0])
    ap.add_argument("version", help="new version, e.g. 0.2.0")
    ap.add_argument("--notes", action="store_true", help="print the CHANGELOG section of this version and exit")
    args = ap.parse_args(argv)
    try:
        if args.notes:
            print(changelog_section(args.version, root))
            return 0
        from kb_distillery.git.ship import current_branch
        cmds = prepare(args.version, root, branch=current_branch(root))
    except ReleaseError as e:
        print(f"error: {e}")
        return 1
    print(f"bumped pyproject.toml and CHANGELOG.md to {args.version}. Next, in order (the tag and push are yours):")
    for c in cmds:
        print(f"  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
