"""Auto-resolve a merge whose only conflicts are in the feature-flag files.

Every PR appends a `[[flag]]` block to the base kit's `flags.toml`, so parallel PRs always conflict there (and in
the files generated from it). The resolution is mechanical: keep every block from both sides (by name, ours first,
then the new ones from theirs), regenerate the frontend files with `flags-gen`, and re-pin the `FlagName` union
in `tests/config/flags/test_flags.py`. Any other conflicting file means "not resolvable": the caller behaves as
before and leaves the merge for a human.
"""
from __future__ import annotations

import re
from pathlib import Path

from kb_distillery.config.flags import codegen
from kb_distillery.ops.daily_sync import run_git

FLAGS_TOML = "src/kb_distillery/kits/base/defaults/flags.toml"
FLAGS_TEST = "tests/config/flags/test_flags.py"
FLAG_FILES = frozenset({
    FLAGS_TOML, FLAGS_TEST, str(codegen.GEN_TS), str(codegen.GEN_WORKER),
    *(str(codegen.modules_path(e)) for e in codegen.SHARE_ENVS),
})
_BLOCK = "[[flag]]"
_NAME = re.compile(r'^name\s*=\s*"([^"]*)"', re.M)
_UNION = re.compile(r"export type FlagName = [^;]*;")
_HUNK = re.compile(r"<<<<<<< [^\n]*\n(.*?)(?:\|\|\|\|\|\|\| [^\n]*\n.*?)?=======\n(.*?)>>>>>>> [^\n]*\n", re.S)


def unmerged_paths(root) -> list[str]:
    return [p for p in run_git(["diff", "--name-only", "--diff-filter=U"], cwd=root).stdout.split("\n") if p]


def _split(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(preamble, [(name, block text)]) of a flags.toml. The comment lines right above a `[[flag]]` header belong to
    that block, not to the one before it."""
    lines = text.split("\n")
    heads = [i for i, ln in enumerate(lines) if ln.strip() == _BLOCK]
    starts = []
    for h in heads:
        k = h
        while k > 0 and lines[k - 1].lstrip().startswith("#"):
            k -= 1
        starts.append(k)
    if not heads:
        return text, []
    blocks = []
    for n, st in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        body = "\n".join(lines[st:end]).rstrip("\n")
        m = _NAME.search("\n".join(lines[heads[n]:end]))
        blocks.append((m.group(1) if m else body, body))
    return "\n".join(lines[:starts[0]]).rstrip("\n"), blocks


def _stage(root, n: int, path: str) -> str | None:
    cp = run_git(["show", f":{n}:{path}"], cwd=root)
    return cp.stdout if cp.returncode == 0 else None


_BAIL = object()


def _merge3(base, ours, theirs):
    """Three-way on one unit (None = absent). _BAIL when both sides changed it differently."""
    if ours == theirs:
        return ours
    if ours == base:
        return theirs
    if theirs == base:
        return ours
    return _BAIL


def merge_flags_toml(ours: str, theirs: str, base: str | None = None) -> str | None:
    """Three-way merge of a flags.toml by `[[flag]]` block: ours in file order, then theirs' new blocks. A block changed
    on one side takes that side's text; deleted on one side and untouched on the other is deleted; changed on both
    sides differently (or changed on one and deleted on the other) is None, like the preamble."""
    pre_o, mine = _split(ours)
    pre_t, other = _split(theirs)
    pre_b, bl = _split(base) if base is not None else (None, [])
    pre = _merge3(pre_b, pre_o, pre_t)
    if pre is _BAIL:
        return None
    o, t, b = dict(mine), dict(other), dict(bl)
    names = [n for n, _ in mine] + [n for n, _ in other if n not in o]
    out = []
    for name in dict.fromkeys(names):
        merged = _merge3(b.get(name), o.get(name), t.get(name))
        if merged is _BAIL:
            return None
        if merged is not None:
            out.append(merged)
    head = pre.rstrip("\n") + "\n\n" if pre.strip() else ""
    return head + "\n\n".join(out) + "\n"


def _pin_text(text: str, union_line: str) -> str:
    return _UNION.sub(lambda _m: union_line, text)


def _resolve_pin_file(text: str, union_line: str) -> str | None:
    """test_flags.py with conflict markers: resolvable when the sides differ only in the FlagName union."""
    ok = True

    def hunk(m):
        nonlocal ok
        if _UNION.sub("U", m.group(1)) != _UNION.sub("U", m.group(2)):
            ok = False
        return m.group(1)

    out = _HUNK.sub(hunk, text)
    return _pin_text(out, union_line) if ok and "<<<<<<<" not in out else None


def resolve(root, unmerged: list[str] | None = None) -> bool:
    """Resolve and `git add` a merge whose conflicts are all in flag files. False (tree untouched) otherwise."""
    root = Path(root)
    unmerged = unmerged_paths(root) if unmerged is None else unmerged
    if not unmerged or not set(unmerged) <= FLAG_FILES:
        return False
    toml_path = root / FLAGS_TOML
    try:
        if FLAGS_TOML in unmerged:
            ours, theirs = _stage(root, 2, FLAGS_TOML), _stage(root, 3, FLAGS_TOML)
            if ours is None or theirs is None:
                return False
            merged = merge_flags_toml(ours, theirs, _stage(root, 1, FLAGS_TOML))
            if merged is None:
                return False
            toml_path.write_text(merged, encoding="utf-8", newline="\n")
        if codegen.main(["--flags", str(toml_path)], root=root) != 0:
            raise RuntimeError("flags-gen failed")
        gen = (root / codegen.GEN_TS).read_text(encoding="utf-8")
        union = _UNION.search(gen)
        if union is None:
            raise RuntimeError("no FlagName union")
        pin = root / FLAGS_TEST
        if FLAGS_TEST in unmerged:
            fixed = _resolve_pin_file(pin.read_text(encoding="utf-8"), union.group(0))
            if fixed is None:
                raise RuntimeError("test_flags.py has other conflicts")
            pin.write_text(fixed, encoding="utf-8", newline="\n")
        elif pin.is_file():                 # merged cleanly, but the union may still be stale
            text = pin.read_text(encoding="utf-8")
            if _UNION.search(text) and _pin_text(text, union.group(0)) != text:
                pin.write_text(_pin_text(text, union.group(0)), encoding="utf-8", newline="\n")
                unmerged = [*unmerged, FLAGS_TEST]
    except Exception:
        for p in unmerged:                   # put the conflict markers back
            run_git(["checkout", "-m", "--", p], cwd=root)
        return False
    stage = sorted({*unmerged, *(f for f in FLAG_FILES if (root / f).is_file())})
    return run_git(["add", "--", *stage], cwd=root).returncode == 0
