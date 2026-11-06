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
    """(preamble, [(name, block text)]) of a flags.toml."""
    parts = re.split(r"(?m)^(?=\[\[flag\]\]\s*$)", text)
    blocks = []
    for part in parts[1:]:
        m = _NAME.search(part)
        blocks.append((m.group(1) if m else part, part.rstrip("\n")))
    return parts[0], blocks


def _stage(root, n: int, path: str) -> str | None:
    cp = run_git(["show", f":{n}:{path}"], cwd=root)
    return cp.stdout if cp.returncode == 0 else None


def merge_flags_toml(ours: str, theirs: str, base: str | None = None) -> str | None:
    """Union of the `[[flag]]` blocks: ours in file order, then theirs' new ones; a name once. None when theirs changed
    a block that ours also changed (a real edit conflict, not an append)."""
    pre, mine = _split(ours)
    _, other = _split(theirs)
    base_blocks = dict(_split(base)[1]) if base else {}
    have = {n: t for n, t in mine}
    out = list(mine)
    for name, text in other:
        if name in have:
            if name in base_blocks and text != base_blocks[name] and have[name] != text and have[name] != base_blocks[name]:
                return None
            continue
        if name in base_blocks:        # ours removed it on purpose
            continue
        out.append((name, text))
        have[name] = text
    return pre.rstrip("\n") + "\n\n" + "\n\n".join(t for _, t in out) + "\n"


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
