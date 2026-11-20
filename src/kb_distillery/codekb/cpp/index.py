"""The C++ tier: parse every C/C++ file of the project (tree-sitter, syntax only), build one symbol index over all of
them, and emit the include, symbol and call layers. Needs `pip install "kb-distillery[code]"`."""
from __future__ import annotations

import posixpath
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from kb_distillery.codekb.generic.graph import Graph
from kb_distillery.codekb.generic.index import RepoIndex, fid
from kb_distillery.codekb.generic.project import CPP_EXT

from .parser import Call, CppFile, Decl, Func, MissingParser, base_type

if TYPE_CHECKING:
    from tree_sitter import Node

SKIP_CALLS = {"static_cast", "dynamic_cast", "reinterpret_cast", "const_cast", "sizeof", "alignof", "decltype", "assert",
              "printf", "fprintf", "snprintf", "sprintf", "move", "forward", "make_unique", "make_shared", "size", "empty",
              "begin", "end", "data", "c_str", "push_back", "emplace_back", "clear", "get", "reset", "at", "find", "str"}


@dataclass
class ClassInfo:
    qname: str
    kind: str
    repo: str
    path: str
    line: int
    end: int
    bases: list[str]
    doc: str
    ns: tuple[str, ...]
    fields: dict[str, Decl] = field(default_factory=dict)
    field_file: dict[str, CppFile] = field(default_factory=dict)
    methods: dict[str, list[tuple[CppFile, Func]]] = field(default_factory=lambda: defaultdict(list))


class Index(RepoIndex):
    def __init__(self, base: RepoIndex, verbose: bool = True):
        self.repos, self.sha, self.tracked = base.repos, base.sha, base.tracked
        self.files: dict[tuple[str, str], CppFile] = {}
        self.classes: dict[str, ClassInfo] = {}
        self.short: dict[str, list[str]] = defaultdict(list)
        self.funcs: dict[str, list[tuple[CppFile, Func]]] = defaultdict(list)
        self.free_short: dict[str, set[str]] = defaultdict(set)
        self.method_owners: dict[str, set[str]] = defaultdict(set)
        self.globals: dict[str, list[tuple[Decl, CppFile]]] = defaultdict(list)
        for r in self.repos:
            for path in self.tracked[r.name]:
                if posixpath.splitext(path)[1].lower() in CPP_EXT:
                    try:
                        self.files[(r.name, path)] = CppFile(r.name, path, r.path / path)
                    except MissingParser:
                        raise
                    except Exception as exc:  # a file tree-sitter cannot read is skipped, not fatal
                        if verbose:
                            print(f"  parse failed {r.name}:{path}: {exc}")
            if verbose:
                print(f"  parsed {r.name}@{self.sha[r.name][:8]}: {sum(1 for k in self.files if k[0] == r.name)} C/C++ files")
        self._build()

    # ---- symbol tables
    def _build(self) -> None:
        for (repo, path), cf in self.files.items():
            for d in cf.decls:
                if d.kind in ("class", "struct"):
                    ci = self.classes.get(d.qname)
                    if ci is None:
                        ci = self.classes[d.qname] = ClassInfo(d.qname, d.kind, repo, path, d.line, d.end, d.bases, d.doc, d.ns)
                        self.short[d.qname.split("::")[-1]].append(d.qname)
        for (repo, path), cf in self.files.items():
            for d in cf.decls:
                owner = "::".join(d.ns + d.cls)
                if d.kind == "field" and owner in self.classes:
                    self.classes[owner].fields.setdefault(d.name, d)
                    self.classes[owner].field_file.setdefault(d.name, cf)
                elif d.kind in ("var", "field"):
                    self.globals[d.name].append((d, cf))
            for f in cf.funcs:
                owner = "::".join(f.ns + f.cls)
                self.funcs[f.qname].append((cf, f))
                if owner in self.classes:
                    self.classes[owner].methods[f.name].append((cf, f))
                    self.method_owners[f.name].add(owner)
                else:
                    self.free_short[f.name].add(f.qname)

    # ---- type resolution
    def find_class(self, type_text: str | None, ns: tuple = (), cls: tuple = (), repo: str | None = None) -> str | None:
        if not type_text:
            return None
        if type_text.startswith("call:"):
            fn = type_text[5:]
            scope, _, name = fn.rpartition("::")
            if name == "instance" and scope:
                return self.find_class(scope, ns, cls, repo)
            for q in self._free_candidates(fn, ns):
                for _, f in self.funcs[q]:
                    if f.ret:
                        return self.find_class(f.ret, f.ns, f.cls, repo)
            return None
        t = base_type(type_text)
        if not t or t in ("auto", "void", "int", "bool", "float", "double", "size_t"):
            return None
        scope = ns + cls
        for i in range(len(scope), -1, -1):
            q = "::".join(scope[:i] + (t,))
            if q in self.classes:
                return q
        cands = [q for q in self.short.get(t.split("::")[-1], []) if q.endswith(t)]
        if len(cands) > 1 and repo:
            same = [q for q in cands if self.classes[q].repo == repo]
            cands = same or cands
        return cands[0] if len(cands) == 1 else None

    def field_decl(self, cls_q: str, name: str, depth: int = 0) -> tuple[Decl, CppFile] | None:
        ci = self.classes.get(cls_q)
        if ci is None or depth > 6:
            return None
        if name in ci.fields:
            return ci.fields[name], ci.field_file[name]
        for b in ci.bases:
            bq = self.find_class(b, ci.ns, (), ci.repo)
            if bq:
                r = self.field_decl(bq, name, depth + 1)
                if r:
                    return r
        return None

    def find_method(self, cls_q: str, name: str, depth: int = 0) -> str | None:
        ci = self.classes.get(cls_q)
        if ci is None or depth > 6:
            return None
        if name in ci.methods:
            return f"{cls_q}::{name}"
        for b in ci.bases:
            bq = self.find_class(b, ci.ns, (), ci.repo)
            if bq:
                r = self.find_method(bq, name, depth + 1)
                if r:
                    return r
        return None

    def owner_class(self, f: Func) -> str | None:
        q = "::".join(f.ns + f.cls)
        return q if q in self.classes else None

    def expr_type(self, cf: CppFile, f: Func, node: Node | None, depth: int = 0) -> str | None:
        """Class qname of an expression, as far as syntax allows."""
        if node is None or depth > 6:
            return None
        t = node.type
        own = self.owner_class(f)
        if t == "this":
            return own
        if t in ("identifier", "field_identifier"):
            name = cf.t(node)
            for table in (f.locals, f.params):
                if name in table:
                    return self.find_class(table[name], f.ns, f.cls, cf.repo)
            if own:
                fd = self.field_decl(own, name)
                if fd:
                    return self.find_class(fd[0].type, fd[0].ns, fd[0].cls, cf.repo)
            for d, gcf in sorted(self.globals.get(name, []), key=lambda x: x[1].repo != cf.repo):
                if d.kind == "var":
                    return self.find_class(d.type, d.ns, d.cls, gcf.repo)
            return None
        if t == "qualified_identifier":
            name = cf.t(node).split("::")[-1]
            for d, gcf in sorted(self.globals.get(name, []), key=lambda x: x[1].repo != cf.repo):
                if d.kind == "var":
                    return self.find_class(d.type, d.ns, d.cls, gcf.repo)
            return None
        if t == "field_expression":
            base = self.expr_type(cf, f, node.child_by_field_name("argument"), depth + 1)
            if base:
                fd = self.field_decl(base, cf.t(node.child_by_field_name("field")))
                if fd:
                    return self.find_class(fd[0].type, fd[0].ns, fd[0].cls, cf.repo)
            return None
        if t == "call_expression":
            c = cf.call(node)
            if c.name == "instance" and c.scope:
                return self.find_class(c.scope, f.ns, f.cls, cf.repo)
            target, _ = self.resolve_call(cf, f, c)
            if target:
                for _, tf in self.funcs.get(target, []):
                    if tf.ret:
                        return self.find_class(tf.ret, tf.ns, tf.cls, cf.repo)
            return None
        if t in ("pointer_expression", "parenthesized_expression", "subscript_expression", "unary_expression"):
            inner = node.child_by_field_name("argument") or (node.named_children[0] if node.named_children else None)
            return self.expr_type(cf, f, inner, depth + 1)
        return None

    def _free_candidates(self, name: str, ns: tuple) -> list[str]:
        out = []
        for i in range(len(ns), -1, -1):
            q = "::".join(ns[:i] + tuple(name.split("::")))
            if q in self.funcs:
                out.append(q)
        return out

    def resolve_call(self, cf: CppFile, f: Func, c: Call) -> tuple[str | None, str]:
        own = self.owner_class(f)
        if c.recv is not None:
            fn = c.node.child_by_field_name("function")
            rc = self.expr_type(cf, f, fn.child_by_field_name("argument")) if fn is not None else None
            if rc:
                m = self.find_method(rc, c.name)
                return (m, "typed") if m else (None, "unresolved")
            owners = self.method_owners.get(c.name, set())
            if len(owners) == 1 and c.name not in SKIP_CALLS:
                return f"{next(iter(owners))}::{c.name}", "name-unique"
            return None, "unresolved"
        if c.scope:
            k = self.find_class(c.scope, f.ns, f.cls, cf.repo)
            if k:
                m = self.find_method(k, c.name)
                if m:
                    return m, "exact"
            cands = self._free_candidates(f"{c.scope}::{c.name}", f.ns)
            return (cands[0], "exact") if cands else (None, "unresolved")
        if own:
            m = self.find_method(own, c.name)
            if m:
                return m, "typed"
        cands = self._free_candidates(c.name, f.ns)
        if cands:
            return cands[0], "exact"
        short = self.free_short.get(c.name, set())
        if len(short) == 1 and c.name not in SKIP_CALLS:
            return next(iter(short)), "name-unique"
        return None, "unresolved"

    # ---- include resolution
    ROOTS = ("", "include/", "src/")

    def resolve_include(self, cf: CppFile, target: str) -> tuple[str, str] | None:
        """The tracked file an `#include "x.h"` names: next to the includer, then from the repository root (or its
        `include/` and `src/` folders), then another repository whose `include_prefix` the target starts with."""
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(cf.path), target))
        if rel in self.tracked[cf.repo]:
            return cf.repo, rel
        for root in self.ROOTS:
            if root + target in self.tracked[cf.repo]:
                return cf.repo, root + target
        best = None
        for r in self.repos:
            if not r.include_prefix:
                continue
            prefix = r.include_prefix + "/"
            if target.startswith(prefix) and (best is None or len(prefix) > best[2]):
                best = (r.name, target[len(prefix):], len(prefix))
        if best:
            for root in self.ROOTS:
                if root + best[1] in self.tracked[best[0]]:
                    return best[0], root + best[1]
        return None


def emit_cpp(ix: Index, g: Graph, call_repos: set[str]) -> dict:
    """The include, symbol and call layers of the C/C++ files (the file layer is `generic.index.emit_files`)."""
    stats = defaultdict(int)
    for (repo, path), cf in ix.files.items():
        g.nodes[fid(repo, path)].update(lang="cpp", loc=cf.loc)
    for (repo, path), cf in ix.files.items():
        for target, line, system in cf.includes():
            hit = ix.resolve_include(cf, target)
            if hit:
                g.edge(fid(repo, path), fid(*hit), "includes", "include", repo, path, line)
                stats["include_resolved"] += 1
            elif not system:
                ext = g.node(f"ext:{target}", "external-header", target)
                g.edge(fid(repo, path), ext, "includes", "include", repo, path, line, conf="external")
                stats["include_external"] += 1
    # symbols
    for q, ci in ix.classes.items():
        g.node(f"class:{q}", ci.kind, q, repo=ci.repo, path=ci.path, line=ci.line, end=ci.end, doc=ci.doc, bases=ci.bases,
               n_fields=len(ci.fields), n_methods=len(ci.methods))
        g.edge(fid(ci.repo, ci.path), f"class:{q}", "defines", "symbol", ci.repo, ci.path, ci.line)
        for b in ci.bases:
            bq = ix.find_class(b, ci.ns, (), ci.repo)
            dst = f"class:{bq}" if bq else g.node(f"extclass:{b}", "external-class", b)
            g.edge(f"class:{q}", dst, "inherits", "symbol", ci.repo, ci.path, ci.line, conf="exact" if bq else "external")
        for name, d in ci.fields.items():
            tq = ix.find_class(d.type, d.ns, d.cls, ci.repo)
            if tq and tq != q:
                fcf = ci.field_file[name]
                g.edge(f"class:{q}", f"class:{tq}", "has_member", "symbol", fcf.repo, fcf.path, d.line, via=name)
    for q, defs in ix.funcs.items():
        defs_sorted = sorted(defs, key=lambda x: (not x[1].is_def, x[0].path))
        cf, f = defs_sorted[0]
        own = ix.owner_class(f)
        g.node(f"func:{q}", "method" if own else "function", q, repo=cf.repo, path=cf.path, line=f.line, end=f.end, sig=f.sig,
               doc=next((x[1].doc for x in defs_sorted if x[1].doc), ""), cls=own, access=next((x[1].access for x in defs if x[1].access), ""),
               defined=f.is_def, locs=[[c.repo, c.path, x.line, x.end, "def" if x.is_def else "decl"] for c, x in defs_sorted])
        g.edge(fid(cf.repo, cf.path), f"func:{q}", "defines" if f.is_def else "declares", "symbol", cf.repo, cf.path, f.line)
        for c2, f2 in defs_sorted[1:]:
            g.edge(fid(c2.repo, c2.path), f"func:{q}", "defines" if f2.is_def else "declares", "symbol", c2.repo, c2.path, f2.line)
    for (repo, path), cf in ix.files.items():
        for d in cf.decls:
            if d.kind == "enum":
                g.node(f"enum:{d.qname}", "enum", d.qname, repo=repo, path=path, line=d.line, end=d.end, members=d.members, doc=d.doc)
                g.edge(fid(repo, path), f"enum:{d.qname}", "defines", "symbol", repo, path, d.line)
            elif d.kind == "var" and d.init and not d.cls and ("const" in d.type or "constexpr" in d.type):
                g.node(f"const:{d.qname}", "constant", d.qname, repo=repo, path=path, line=d.line, end=d.end, type=d.type, value=d.init, doc=d.doc)
                g.edge(fid(repo, path), f"const:{d.qname}", "defines", "symbol", repo, path, d.line)
            elif d.kind == "macro" and repo in call_repos:
                g.node(f"macro:{repo}:{d.name}", "macro", d.name, repo=repo, path=path, line=d.line, value=d.init)
    # calls
    for (repo, path), cf in ix.files.items():
        if repo not in call_repos:
            continue
        for f in cf.funcs:
            if not f.is_def:
                continue
            ext: set[str] = set()
            for c in f.calls:
                if c.name in SKIP_CALLS and c.recv is None and not c.scope:
                    continue
                target, conf = ix.resolve_call(cf, f, c)
                stats[f"call_{conf}"] += 1
                if target and target != f.qname:
                    g.edge(f"func:{f.qname}", f"func:{target}", "calls", "call", repo, path, c.line, conf=conf)
                elif target is None and c.scope and not c.scope.startswith("std"):
                    ext.add(f"{c.scope}::{c.name}")
            if ext:
                g.nodes[f"func:{f.qname}"]["ext_calls"] = sorted(ext)[:40]
    return dict(stats)
