"""Source-level rewrites for the restructure: imports, sys.path hacks, root definitions.

Pure functions over text (stdlib `ast` locates statements; edits are made on the original text so
formatting and comments are preserved). Every function returns (new_text, notes) where notes are
human-readable lines for the report (`MANUAL:` prefix = the script could not decide).
"""
import ast
import re

from layout import module_map

_MAP = module_map()
_TOP = {k for k in _MAP if "." not in k}


def _strip_meta(dotted):
    return dotted[5:] if dotted.startswith("meta.") else dotted


def map_dotted(dotted):
    """Longest-prefix mapping of an old dotted module name to its new one, or None."""
    name = _strip_meta(dotted)
    parts = name.split(".")
    for n in range(len(parts), 0, -1):
        head = ".".join(parts[:n])
        if head in _MAP:
            return ".".join([_MAP[head]] + parts[n:])
    return None


def _is_old_import(dotted):
    return map_dotted(dotted) is not None


def _split_package(new_dotted):
    mod, _, leaf = new_dotted.rpartition(".")
    return mod, leaf


# ----------------------------------------------------------------------------------------------
def rewrite_imports(text, own_pkg_old=None, own_pkg_new=None, siblings=()):
    """Rewrite absolute imports of moved modules to `kb.*`.

    own_pkg_old/new: dotted package of this file before/after (e.g. 'dashboard' -> 'kb.dashboard'),
    used to turn relative imports of siblings that left the package into absolute ones.
    """
    notes = []
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return text, [f"MANUAL: cannot parse ({e})"]
    lines = text.split("\n")
    edits = []  # (start_line, end_line, new_lines)  1-based inclusive

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            indent = " " * node.col_offset
            tail = lines[node.end_lineno - 1][node.end_col_offset:]
            if node.level == 0 and node.module == "meta":
                stmts = []
                for al in node.names:
                    new = map_dotted("meta." + al.name)
                    if new is None:
                        notes.append(f"MANUAL: line {node.lineno}: unmapped `from meta import {al.name}`")
                        stmts.append(f"{indent}from meta import {al.name}")
                        continue
                    pkg, leaf = _split_package(new)
                    local = al.asname or al.name
                    stmts.append(f"{indent}from {pkg} import {leaf}" + (f" as {local}" if local != leaf else ""))
                edits.append((node.lineno, node.end_lineno, _join_tail(stmts, tail)))
            elif node.level == 0 and node.module and node.module.split(".")[0] in siblings and map_dotted(node.module) is None:
                names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
                edits.append((node.lineno, node.end_lineno, _join_tail([f"{indent}from .{node.module} import {names}"], tail)))
            elif node.level == 0 and node.module:
                new_mod = map_dotted(node.module)
                if new_mod is None:
                    if node.module.split(".")[0] == "meta":
                        notes.append(f"MANUAL: line {node.lineno}: unmapped import of {node.module}")
                    continue
                if _needs_split(node, new_mod):
                    stmts = _from_stmts(node, new_mod, indent)
                    edits.append((node.lineno, node.end_lineno, _join_tail(stmts, tail)))
                else:
                    first = lines[node.lineno - 1]
                    fixed = re.sub(r"(\bfrom\s+)" + re.escape(node.module) + r"(?=\s)", lambda m: m.group(1) + new_mod, first, count=1)
                    block = [fixed] + lines[node.lineno:node.end_lineno]
                    block[-1] = _strip_noqa_e402(block[-1])
                    edits.append((node.lineno, node.end_lineno, block))
            elif node.level == 0 and node.module is None:
                continue
            elif node.level > 0 and own_pkg_old and own_pkg_new:
                # relative import: sibling module that moved to another package -> absolute
                base_old = own_pkg_old.split(".")
                if node.level > len(base_old) + 0 and node.level - 1 > len(base_old):
                    continue
                anchor = base_old[: len(base_old) - (node.level - 1)] if node.level > 1 else base_old
                if node.module:
                    old_full = ".".join(anchor + [node.module])
                    new_full = map_dotted(old_full)
                    if new_full and new_full.rsplit(".", 1)[0] != _own_new_anchor(own_pkg_new, node.level, own_pkg_old):
                        stmts = _from_stmts(node, new_full, indent, relative_origin=True)
                        edits.append((node.lineno, node.end_lineno, _join_tail(stmts, tail)))
                else:
                    # `from . import a, b`: names are sibling modules
                    out, changed = [], False
                    for al in node.names:
                        old_full = ".".join(anchor + [al.name])
                        new_full = map_dotted(old_full)
                        stay = _own_new_anchor(own_pkg_new, node.level, own_pkg_old)
                        if new_full and new_full.rsplit(".", 1)[0] != stay:
                            pkg, leaf = _split_package(new_full)
                            out.append(f"{indent}from {pkg} import {leaf}" + (f" as {al.asname or al.name}" if (al.asname or leaf != al.name) else ""))
                            changed = True
                        else:
                            out.append(None)
                    if changed:
                        keep = [al for al, o in zip(node.names, out) if o is None]
                        stmts = [o for o in out if o]
                        if keep:
                            names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in keep)
                            stmts.insert(0, f"{indent}from {'.' * node.level} import {names}")
                        edits.append((node.lineno, node.end_lineno, _join_tail(stmts, tail)))
        elif isinstance(node, ast.Import):
            indent = " " * node.col_offset
            tail = lines[node.end_lineno - 1][node.end_col_offset:]
            stmts, changed = [], False
            for al in node.names:
                new = map_dotted(al.name)
                if new is None and al.name.split(".")[0] in siblings and "." not in al.name:
                    changed = True
                    stmts.append(f"{indent}from . import {al.name}" + (f" as {al.asname}" if al.asname else ""))
                    continue
                if new is None:
                    stmts.append(f"{indent}import {al.name}" + (f" as {al.asname}" if al.asname else ""))
                    continue
                changed = True
                if "." not in al.name or al.name.split(".")[0] != "meta" and al.name in _TOP:
                    # `import lint` -> `from kb.lint import lint` (binds the same local name)
                    pkg, leaf = _split_package(new)
                    local = al.asname or al.name
                    stmts.append(f"{indent}from {pkg} import {leaf}" + (f" as {local}" if local != leaf else ""))
                elif al.asname:
                    stmts.append(f"{indent}import {new} as {al.asname}")
                else:
                    notes.append(f"MANUAL: line {node.lineno}: `import {al.name}` binds a package name; rewritten to `import {new}`")
                    stmts.append(f"{indent}import {new}")
            if changed:
                edits.append((node.lineno, node.end_lineno, _join_tail(stmts, tail)))

    for start, end, new_lines in sorted(edits, key=lambda e: -e[0]):
        lines[start - 1:end] = new_lines
    out = "\n".join(lines)
    if edits:
        notes.append(f"COUNT:imports:{len(edits)}")
    return out, notes


def _needs_split(node, new_mod):
    old_mod = _strip_meta(node.module)
    for al in node.names:
        if al.name == "*":
            continue
        sub_new = map_dotted(f"{old_mod}.{al.name}")
        if sub_new and sub_new.rsplit(".", 1)[0] != new_mod:
            return True
    return False


def _strip_noqa_e402(line):
    """The sys.path hack that needed `# noqa: E402` is gone; drop the now-misleading marker."""
    return re.sub(r"\s*#\s*noqa:\s*E402(\s*\(.*\))?\s*$", "", line)


def _own_new_anchor(own_pkg_new, level, own_pkg_old):
    parts = own_pkg_new.split(".")
    return ".".join(parts[: len(parts) - (level - 1)]) if level > 1 else own_pkg_new


def _join_tail(stmts, tail):
    stmts = list(stmts)
    if tail.strip():
        stmts[-1] = _strip_noqa_e402(stmts[-1] + tail)
    return stmts


def _from_stmts(node, new_mod, indent, relative_origin=False):
    """Statements replacing `from <old> import names`. Names that are submodules which moved to a
    different package are imported from that package with the old local name kept as alias."""
    stmts, keep = [], []
    old_mod = _strip_meta(node.module)
    for al in node.names:
        sub_old = f"{old_mod}.{al.name}"
        sub_new = map_dotted(sub_old) if al.name != "*" else None
        if sub_new and sub_new.rsplit(".", 1)[0] != new_mod and not relative_origin_same(new_mod, sub_new):
            pkg, leaf = _split_package(sub_new)
            local = al.asname or al.name
            stmts.append(f"{indent}from {pkg} import {leaf}" + (f" as {local}" if local != leaf else ""))
        else:
            keep.append(al)
    if keep or not stmts:
        names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in keep)
        # keep multi-line parenthesised layout simple: single logical line
        stmts.insert(0, f"{indent}from {new_mod} import {names}")
    return stmts


def relative_origin_same(new_mod, sub_new):
    return sub_new.rsplit(".", 1)[0] == new_mod


# ----------------------------------------------------------------------------------------------
_SYSPATH_INSERT = re.compile(r"^\s*sys\.path\.insert\(")


def remove_sys_path_hacks(text, strict=True):
    """Delete every `sys.path.insert(...)` statement (and a guarding `if x not in sys.path:`)."""
    notes = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text, []
    lines = text.split("\n")
    kill = []  # (start, end) 1-based inclusive

    location_arg = re.compile(r"__file__|\b(root|meta\w*|here|base\w*|code_dir)\b|dirname|['\"]meta['\"]|['\"](ingest|dashboard|share)['\"]", re.I)

    def is_insert(n):
        ok = (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
              and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "insert"
              and isinstance(n.value.func.value, ast.Attribute) and n.value.func.value.attr == "path"
              and isinstance(n.value.func.value.value, ast.Name) and n.value.func.value.value.id == "sys")
        if ok and not strict and len(n.value.args) == 2 and not location_arg.search(ast.unparse(n.value.args[1])):
            return False       # a temp dir or argv path put on sys.path on purpose: not a layout hack
        return ok

    def guarded(n):
        # if X not in sys.path:  <insert>
        if isinstance(n, ast.If) and len(n.body) == 1 and not n.orelse and is_insert(n.body[0]):
            t = n.test
            return (isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.NotIn)
                    and "sys.path" in ast.unparse(t.comparators[0]))
        return False

    def visit(body, parent_is_block):
        removed_all = True
        for n in list(body):
            if guarded(n) or is_insert(n):
                kill.append((n.lineno, n.end_lineno))
                continue
            removed_all = False
            for field in ("body", "orelse", "finalbody", "handlers"):
                sub = getattr(n, field, None)
                if isinstance(sub, list) and sub and isinstance(sub[0], ast.stmt):
                    visit(sub, True)
                elif isinstance(sub, list):
                    for h in sub:
                        if isinstance(h, ast.ExceptHandler):
                            visit(h.body, True)
        return removed_all

    # blocks whose whole body would vanish need a `pass`
    def fix_empty(n):
        for field in ("body", "orelse", "finalbody"):
            sub = getattr(n, field, None)
            if isinstance(sub, list) and sub and all(is_insert(s) or guarded(s) for s in sub) and not isinstance(n, ast.Module):
                first = sub[0]
                ind = " " * first.col_offset
                kill.append(("pass", first.lineno, ind))

    visit(tree.body, False)
    for n in ast.walk(tree):
        if hasattr(n, "body") and not isinstance(n, ast.Module):
            fix_empty(n)
    passes = {k[1]: k[2] for k in kill if k[0] == "pass"}
    spans = sorted((k for k in kill if k[0] != "pass"), key=lambda k: -k[0])
    for s, e in spans:
        if s in passes:
            lines[s - 1:e] = [passes[s] + "pass"]
        else:
            # drop the statement; also drop one directly preceding standalone comment about the path
            lines[s - 1:e] = []
        notes.append(f"removed sys.path hack at line {s}")
    return "\n".join(lines), notes


# ----------------------------------------------------------------------------------------------
_DEF = re.compile(
    r'^(?P<ind>[ \t]*)(?P<name>[A-Za-z_]\w*)\s*=\s*(?:os\.environ\.get\("KB_ROOT"\)\s+or\s+)?'
    r'os\.path\.dirname\((?P<inner>(?:os\.path\.dirname\()*)os\.path\.abspath\(__file__\)(?P<close>\)+)'
    r'(?P<tail>\s*#.*)?$')


def rewrite_root_defs(text, old_depth):
    """`X = os.path.dirname(...abspath(__file__))` -> kb.paths.vault_root().

    old_depth = directories below the old code dir `meta/` the file sat in (meta/x.py -> 0).
    Level 1 (relative to the file's own dir) names the vault ROOT -> `X = vault_root()`; level 0 names the old
    code dir `meta/` (now vault metadata) -> `X = os.path.join(vault_root(), "meta")`. Calls (not imported
    constants) so a module reloaded under a different $KB_ROOT follows it, as the old definitions did.
    """
    notes = []
    out = []
    imported = False
    for i, line in enumerate(text.split("\n"), 1):
        m = _DEF.match(line)
        if not m:
            out.append(line)
            continue
        d = 1 + m.group("inner").count("os.path.dirname(")
        rel = d - (old_depth + 1)
        ind, name = m.group("ind"), m.group("name")
        if rel == 1:
            rhs = "vault_root()"
        elif rel == 0:
            rhs = 'os.path.join(vault_root(), "meta")'
        else:
            notes.append(f"MANUAL: line {i}: unexpected dirname depth for {name}: {line.strip()}")
            out.append(line)
            continue
        if not imported:
            out.append(f"{ind}from kb.paths import vault_root")
            imported = True
        out.append(f"{ind}{name} = {rhs}" + (m.group("tail") or ""))
        notes.append(f"root def `{name}` -> vault_root()")
    return "\n".join(out), notes


def simplify_root(text):
    """`META = os.path.join(vault_root(), "meta")` + `ROOT = os.path.dirname(META)` -> `ROOT = vault_root()`;
    the META definition stays only if the file still uses it."""
    mdef = re.compile(r'^(?P<ind>[ \t]*)(?P<name>[A-Za-z_]\w*) = os\.path\.join\(vault_root\(\), "meta"\)(?P<tail>[ \t]*#.*)?[ \t]*$', re.M)
    for m in list(mdef.finditer(text)):
        name = m.group("name")
        rx = re.compile(r'^(?P<ind>[ \t]*)(?P<n2>[A-Za-z_]\w*) = (?:os\.environ\.get\(.KB_ROOT.\) or )?os\.path\.dirname\(%s\)[ \t]*$' % re.escape(name), re.M)
        if not rx.search(text):
            continue
        text = rx.sub(lambda r: f"{r.group('ind')}{r.group('n2')} = vault_root()", text)
        body = mdef.sub("", text)
        if not re.search(r"\b%s\b" % re.escape(name), body):
            text = mdef.sub(lambda r: "" if r.group("name") == name else r.group(0), text, count=0)
            text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text


_PATHS_IMPORT = re.compile(r"^from kb\.paths import (?P<names>[^\n#]+?)[ \t]*$", re.M)


def prune_paths_imports(text):
    """Drop names imported from kb.paths that the file never uses."""
    def fix(m):
        keep = []
        body = text[:m.start()] + text[m.end():]
        for item in [n.strip() for n in m.group("names").split(",")]:
            local = item.split(" as ")[-1].strip()
            if re.search(r"\b%s\b" % re.escape(local), body):
                keep.append(item)
        return "from kb.paths import " + ", ".join(keep) if keep else "\0DROP\0"
    out = _PATHS_IMPORT.sub(fix, text)
    return re.sub(r"\0DROP\0\n?", "", out)
