"""Python tier: the same layers the C++ tier emits (include, symbol, call, config), read with the standard `ast` module.

    include  file -> file for an `import` that resolves inside the indexed repos; other packages as `external-module`
    symbol   file defines class / function / method; class inherits class
    call     function -> function (the callee resolved through the module's own names, its imports, or `self.`);
             file -runs-> file when a script names another script of the repos in a string (subprocess, os.system)
    config   argparse / click options a file defines, environment variables it reads

Node ids match the C++ tier (`class:<qname>`, `func:<qname>`, `file:<repo>:<path>`) with dotted Python names, so the
cards, the staleness diff and the artifact graph need no Python-specific code. No import of the indexed code is ever
executed: a file that does not parse (Python 2, templates) is skipped and counted.
"""
from __future__ import annotations

import ast
import posixpath
import re
import sys
import warnings
from collections import defaultdict

from kb_distillery.codekb.generic.index import RepoIndex as Index, fid
from kb_distillery.codekb.generic.graph import Graph

STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
SCRIPT = re.compile(r"(?<![\w.-])([\w./-]*?[\w-]+\.py)\b")
ADD_ARG = {"add_argument", "add_option"}
GENERIC_NAMES = {"main", "run", "get", "set", "init", "load", "save", "open", "close", "read", "write", "start", "stop", "update",
                 "parse", "build", "check", "test", "setup", "call", "exec", "execute", "process", "handle", "format", "print", "log"}


def module_name(path: str) -> str:
    """Dotted module of a file. A hyphen reads as an underscore: files copied into a folder are often renamed that way."""
    mod = posixpath.splitext(path)[0].replace("/", ".").replace("-", "_")
    return mod[: -len(".__init__")] if mod.endswith(".__init__") else mod


class PyFile:
    def __init__(self, repo: str, path: str, text: str):
        self.repo, self.path, self.mod = repo, path, module_name(path)
        self.loc = text.count("\n") + 1
        with warnings.catch_warnings():  # the indexed code's own SyntaxWarnings are not ours to print
            warnings.simplefilter("ignore")
            self.tree = ast.parse(text)
        self.classes: dict[str, ast.ClassDef] = {}
        self.funcs: dict[str, ast.AST] = {}          # qualified inside the module: f, C.m, C.Inner.m
        self.owner: dict[str, str | None] = {}       # function -> class (qualified inside the module) or None
        self.imports: list[tuple[str, str | None, str, int, int]] = []  # (module, name, alias, level, line)
        self.entry = False
        self._walk(self.tree.body, "", None)

    def _walk(self, body: list[ast.stmt], prefix: str, cls: str | None) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                q = prefix + node.name
                self.classes[q] = node
                self._walk(node.body, q + ".", q)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = prefix + node.name
                self.funcs[q] = node
                self.owner[q] = cls
            elif isinstance(node, ast.Import) and not prefix:
                for a in node.names:
                    self.imports.append((a.name, None, a.asname or a.name.split(".")[0], 0, node.lineno))
            elif isinstance(node, ast.ImportFrom) and not prefix:
                for a in node.names:
                    self.imports.append((node.module or "", a.name, a.asname or a.name, node.level, node.lineno))
            elif isinstance(node, (ast.If, ast.Try)) and not prefix:
                if isinstance(node, ast.If) and _is_main_guard(node.test):
                    self.entry = True
                for part in ("body", "orelse", "finalbody"):
                    self._walk([n for n in getattr(node, part, []) if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef))], prefix, cls)
                for h in getattr(node, "handlers", []):
                    self._walk([n for n in h.body if isinstance(n, (ast.Import, ast.ImportFrom))], prefix, cls)


def _is_main_guard(test: ast.expr) -> bool:
    return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__"
            and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in test.comparators))


def _sig(node: ast.AST) -> str:
    try:
        args = ast.unparse(node.args)  # type: ignore[attr-defined]
    except Exception:
        args = "..."
    ret = f" -> {ast.unparse(node.returns)}" if getattr(node, "returns", None) is not None else ""
    return f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}({args}){ret}"  # type: ignore[attr-defined]


def _doc(node: ast.AST) -> str:
    d = ast.get_docstring(node, clean=True) or ""  # type: ignore[arg-type]
    return re.sub(r"\s+", " ", d.split("\n\n")[0])[:240]


def _dotted(node: ast.expr) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class PyIndex:
    def __init__(self, ix: Index, verbose: bool = False):
        self.ix = ix
        self.files: dict[tuple[str, str], PyFile] = {}
        self.failed: list[str] = []
        self.by_mod: dict[str, list[PyFile]] = defaultdict(list)       # full dotted module and every dotted suffix of it
        self.by_base: dict[str, list[PyFile]] = defaultdict(list)      # script file name -> files
        self.method_short: dict[str, list[str]] = defaultdict(list)
        for r in ix.repos:
            for path in ix.tracked[r.name]:
                if not path.endswith(".py"):
                    continue
                try:
                    pf = PyFile(r.name, path, (r.path / path).read_text(encoding="utf-8", errors="replace"))
                except (SyntaxError, ValueError, RecursionError):
                    self.failed.append(f"{r.name}:{path}")
                    continue
                self.files[(r.name, path)] = pf
                parts = pf.mod.split(".")
                for i in range(len(parts)):
                    self.by_mod[".".join(parts[i:])].append(pf)
                self.by_base[posixpath.basename(path)].append(pf)
            if verbose:
                print(f"  parsed {r.name}: {sum(1 for k in self.files if k[0] == r.name)} Python files")
        for pf in self.files.values():
            for q in pf.funcs:
                if pf.owner[q]:
                    self.method_short[q.split(".")[-1]].append(f"{pf.mod}.{q}")

    # ---- resolution
    def module(self, pf: PyFile, mod: str, level: int = 0) -> PyFile | None:
        """The indexed file an import names: relative imports from the importer's package, then the same repo, then any."""
        if level:
            base = pf.mod.split(".")
            base = base[: len(base) - level + (1 if pf.path.endswith("__init__.py") else 0)]
            mod = ".".join([p for p in base if p] + ([mod] if mod else []))
        if not mod:
            return None
        cands = self.by_mod.get(mod, [])
        here = posixpath.dirname(pf.path)
        if not level and mod.split(".")[0] in STDLIB:  # `import logging` is the standard library unless a file shadows it
            cands = [c for c in cands if c.mod == mod or posixpath.dirname(c.path) == here]
        if not cands:
            return None
        return sorted(cands, key=lambda c: (c.repo != pf.repo, posixpath.dirname(c.path) != here, len(c.mod) - len(mod), c.path))[0]

    def names(self, pf: PyFile) -> dict[str, tuple[PyFile, str | None]]:
        """Names a module binds by import: alias -> (file, name inside it or None for the module itself)."""
        out: dict[str, tuple[PyFile, str | None]] = {}
        for mod, name, alias, level, _ in pf.imports:
            if name is None:
                t = self.module(pf, mod, level)
                if t:  # `import a.b` binds the name a.b; `import a.b as x` binds x
                    out[alias if alias != mod.split(".")[0] else mod] = (t, None)
            else:
                sub = self.module(pf, f"{mod}.{name}" if mod else name, level)
                if sub:
                    out[alias] = (sub, None)
                    continue
                t = self.module(pf, mod, level)
                if t:
                    out[alias] = (t, name)
        return out

    def target(self, pf: PyFile, names: dict, cls: str | None, call: ast.Call) -> tuple[str | None, str]:
        """(qualified callee, confidence) or (None, '')."""
        f = call.func
        if isinstance(f, ast.Name):
            if f.id in pf.funcs:
                return f"{pf.mod}.{f.id}", "exact"
            if f.id in pf.classes:
                return (f"{pf.mod}.{f.id}.__init__", "exact") if f"{f.id}.__init__" in pf.funcs else (None, "")
            if f.id in names:
                t, name = names[f.id]
                if name and name in t.funcs:
                    return f"{t.mod}.{name}", "import"
                if name and name in t.classes and f"{name}.__init__" in t.funcs:
                    return f"{t.mod}.{name}.__init__", "import"
            return None, ""
        if isinstance(f, ast.Attribute):
            recv = _dotted(f.value)
            if recv in ("self", "cls") and cls:
                hit = self.method(pf, cls, f.attr)
                if hit:
                    return hit, "typed"
            if recv and recv in names:
                t, name = names[recv]
                if name is None and f.attr in t.funcs:
                    return f"{t.mod}.{f.attr}", "import"
                if name is None and f.attr in t.classes and f"{f.attr}.__init__" in t.funcs:
                    return f"{t.mod}.{f.attr}.__init__", "import"
                if name and f"{name}.{f.attr}" in t.funcs:
                    return f"{t.mod}.{name}.{f.attr}", "import"
            if recv and recv in pf.classes and f"{recv}.{f.attr}" in pf.funcs:
                return f"{pf.mod}.{recv}.{f.attr}", "exact"
            # `obj.method()` on an object of unknown type: accepted only when one class in the index has that method
            cands = self.method_short.get(f.attr, [])
            if recv not in names and len(cands) == 1 and f.attr not in GENERIC_NAMES and len(f.attr) > 3 and not f.attr.startswith("_"):
                return cands[0], "name-unique"
        return None, ""

    def method(self, pf: PyFile, cls: str, name: str, depth: int = 0) -> str | None:
        if f"{cls}.{name}" in pf.funcs:
            return f"{pf.mod}.{cls}.{name}"
        if depth > 6 or cls not in pf.classes:
            return None
        names = self.names(pf)
        for b in pf.classes[cls].bases:
            hit = self.base(pf, names, b)
            if hit:
                got = self.method(hit[0], hit[1], name, depth + 1)
                if got:
                    return got
        return None

    def base(self, pf: PyFile, names: dict, node: ast.expr) -> tuple[PyFile, str] | None:
        d = _dotted(node)
        if not d:
            return None
        if d in pf.classes:
            return pf, d
        head, _, tail = d.partition(".")
        if head in names:
            t, name = names[head]
            q = ".".join(x for x in (name, tail) if x)
            if q in t.classes:
                return t, q
        return None


def emit_python(ix: Index, g: Graph, call_repos: set[str], verbose: bool = False) -> dict:
    stats: dict[str, int] = defaultdict(int)
    px = PyIndex(ix, verbose)
    if px.failed:
        stats["parse_failed"] = len(px.failed)
        g.meta.setdefault("warnings", []).append(
            f"{len(px.failed)} Python file(s) do not parse with Python {sys.version_info.major}.{sys.version_info.minor} and were skipped: "
            + ", ".join(px.failed[:5]) + (" ..." if len(px.failed) > 5 else ""))
    for (repo, path), pf in px.files.items():
        f_id = fid(repo, path)
        n = g.nodes.get(f_id)
        if n is not None:
            n.update(lang="python", loc=pf.loc, **({"entry": True} if pf.entry else {}))
        stats["files"] += 1
        names = px.names(pf)
        # ---- imports
        seen: set[tuple] = set()
        for mod, name, _alias, level, line in pf.imports:
            t = (px.module(pf, f"{mod}.{name}" if (name and mod) else (name or mod), level) if name else None) or px.module(pf, mod, level)
            if t is not None:
                if (t.repo, t.path) != (repo, path) and (t.repo, t.path) not in seen:
                    seen.add((t.repo, t.path))
                    g.edge(f_id, fid(t.repo, t.path), "includes", "include", repo, path, line)
                    stats["import_resolved"] += 1
                continue
            top = (mod or name or "").split(".")[0]
            if level or not top or top in STDLIB:
                stats["import_stdlib" if top in STDLIB else "import_unresolved"] += 1
                continue
            if top not in seen:
                seen.add(top)
                g.edge(f_id, g.node(f"ext:py:{top}", "external-module", top), "includes", "include", repo, path, line, conf="external")
                stats["import_external"] += 1
        # ---- symbols
        for q, node in pf.classes.items():
            cq = f"{pf.mod}.{q}"
            meths = [m for m in pf.funcs if pf.owner[m] == q]
            g.node(f"class:{cq}", "class", cq, repo=repo, path=path, line=node.lineno, end=node.end_lineno, doc=_doc(node), lang="python",
                   bases=[ast.unparse(b) for b in node.bases], n_methods=len(meths),
                   n_fields=sum(1 for s in node.body if isinstance(s, (ast.Assign, ast.AnnAssign))), primary=True)
            g.edge(f_id, f"class:{cq}", "defines", "symbol", repo, path, node.lineno)
            for b in node.bases:
                hit = px.base(pf, names, b)
                label = ast.unparse(b)
                if hit:
                    g.edge(f"class:{cq}", f"class:{hit[0].mod}.{hit[1]}", "inherits", "symbol", repo, path, node.lineno)
                elif label not in ("object",):
                    g.edge(f"class:{cq}", g.node(f"extclass:py:{label}", "external-class", label), "inherits", "symbol", repo, path, node.lineno, conf="external")
            stats["classes"] += 1
        for q, node in pf.funcs.items():
            fq, own = f"{pf.mod}.{q}", pf.owner[q]
            g.node(f"func:{fq}", "method" if own else "function", fq, repo=repo, path=path, line=node.lineno, end=node.end_lineno, sig=_sig(node),
                   doc=_doc(node), cls=f"{pf.mod}.{own}" if own else None, lang="python", defined=True,
                   access="private" if node.name.startswith("_") and not node.name.startswith("__") else "public", primary=True)
            g.edge(f_id, f"func:{fq}", "defines", "symbol", repo, path, node.lineno)
            stats["functions"] += 1
        # ---- calls, options, environment
        scopes: list[tuple[str | None, str | None, list[ast.AST]]] = [(None, None, _module_level(pf.tree))]
        scopes += [(q, pf.owner[q], [node]) for q, node in pf.funcs.items()]
        for q, own, roots in scopes:
            src = f"func:{pf.mod}.{q}" if q else f_id
            for root in roots:
                for node in _walk_own(root):
                    if isinstance(node, ast.Call):
                        if repo in call_repos and q:
                            target, conf = px.target(pf, names, own, node)
                            if target and target != f"{pf.mod}.{q}":
                                g.edge(src, f"func:{target}", "calls", "call", repo, path, node.lineno, conf=conf)
                                stats[f"call_{conf}"] += 1
                            elif not target:
                                stats["call_unresolved"] += 1
                        _config(g, node, src, repo, path, stats)
                    elif isinstance(node, ast.Subscript) and _dotted(node.value) == "os.environ":
                        key = node.slice if isinstance(node.slice, ast.Constant) else None
                        if key is not None and isinstance(key.value, str):
                            g.edge(src, g.node(f"env:{key.value}", "env-var", key.value), "reads_env", "config", repo, path, node.lineno)
                            stats["env"] += 1
        # ---- scripts this file names in a string (it starts them, or tells the reader to)
        mine = posixpath.basename(path)
        for node in ast.walk(pf.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and ".py" in node.value and len(node.value) < 400:
                for m in SCRIPT.finditer(node.value):
                    base = posixpath.basename(m.group(1))
                    cands = px.by_base.get(base, [])
                    if base != mine and len(cands) == 1:
                        t = cands[0]
                        g.edge(f_id, fid(t.repo, t.path), "runs", "call", repo, path, node.lineno, conf="syntactic")
                        stats["script_runs"] += 1
    return dict(stats)


def _module_level(tree: ast.Module) -> list[ast.AST]:
    return [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def _walk_own(root: ast.AST):
    """Every node under `root`, not descending into nested functions or classes (they are their own scopes)."""
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    stack = [c for c in ast.iter_child_nodes(root) if not isinstance(c, nested)] if isinstance(root, nested) else [root]
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                stack.append(child)


def _config(g: Graph, call: ast.Call, src: str, repo: str, path: str, stats: dict) -> None:
    f = call.func
    name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
    dotted = _dotted(f) or ""
    strs = [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    if name in ADD_ARG or dotted.endswith(("click.option", "click.argument")) or name == "option":
        flags = [s for s in strs if s.startswith("-")]
        if not flags:
            return
        flag = max(flags, key=len)
        doc = next((k.value.value for k in call.keywords if k.arg == "help" and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)), "")
        default = next((ast.unparse(k.value) for k in call.keywords if k.arg == "default"), None)
        g.edge(src, g.node(f"flag:{repo}:{path}:{flag}", "flag", flag, repo=repo, path=path, line=call.lineno,
                           doc=re.sub(r"\s+", " ", doc)[:200], default=default, aliases=sorted(x for x in flags if x != flag)),
               "defines", "config", repo, path, call.lineno)
        stats["options"] += 1
    elif dotted in ("os.getenv", "os.environ.get", "environ.get", "getenv") and strs:
        g.edge(src, g.node(f"env:{strs[0]}", "env-var", strs[0]), "reads_env", "config", repo, path, call.lineno)
        stats["env"] += 1
