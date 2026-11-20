"""tree-sitter helpers: one parsed C++ file -> includes, declarations with scope, functions with their calls.

No preprocessing and no compile database: a code base need not build on this machine, so everything here is
syntactic. Each fact keeps its line, which is what makes it citable.

tree-sitter is an optional dependency (`pip install "kb-distillery[code]"`): nothing here imports it until a C++ file is
parsed, so the Python tier and every other command work without it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from tree_sitter import Node

_PARSER = None


class MissingParser(RuntimeError):
    """tree-sitter or its C++ grammar is not installed."""


def parser():
    """The C++ parser, built on first use."""
    global _PARSER
    if _PARSER is None:
        try:
            import tree_sitter_cpp
            from tree_sitter import Language, Parser
        except ImportError as exc:
            raise MissingParser('the C++ tier needs tree-sitter: pip install "kb-distillery[code]"') from exc
        _PARSER = Parser(Language(tree_sitter_cpp.language()))
    return _PARSER

INCLUDE_RE = re.compile(rb'^[ \t]*#[ \t]*include[ \t]+(["<])([^">]+)[">]', re.M)
SCOPE_TYPES = {"class_specifier", "struct_specifier", "union_specifier"}
TRANSPARENT = {
    "template_declaration", "preproc_ifdef", "preproc_if", "preproc_else", "preproc_elif", "preproc_elifdef",
    "declaration_list", "linkage_specification", "field_declaration_list",
}
TYPE_NOISE = re.compile(r"\b(const|constexpr|static|inline|volatile|mutable|struct|class|typename|extern)\b")


def strip_template(name: str) -> str:
    return re.sub(r"<.*>\s*$", "", name).strip()


def base_type(type_text: str) -> str:
    """'const std::vector<Foo*>&' -> 'Foo'; 'std::unique_ptr<ns::Bar>' -> 'ns::Bar'; 'ns::Box<>' -> 'ns::Box'."""
    t = TYPE_NOISE.sub(" ", type_text).replace("&", " ").replace("*", " ").strip()
    m = re.match(r"^(?:std::)?(?:unique_ptr|shared_ptr|vector|optional|array|span)\s*<\s*([^,>]+)", t)
    if m:
        t = m.group(1).strip()
    return strip_template(t).strip()


@dataclass
class Call:
    name: str  # last component: method or function name
    recv: str | None  # receiver expression text for a.b() / a->b()
    scope: str | None  # qualifier for A::b()
    line: int
    node: Node
    args: list[Node]
    in_lambda: bool


@dataclass
class Func:
    qname: str
    name: str
    ns: tuple[str, ...]
    cls: tuple[str, ...]
    line: int
    end: int
    sig: str
    ret: str
    params: dict[str, str]
    doc: str
    node: Node
    body: Node | None
    is_def: bool
    access: str = ""
    locals: dict[str, str] = field(default_factory=dict)
    local_init: dict[str, Node] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)


@dataclass
class Decl:
    kind: str  # class | struct | enum | field | var | macro | alias
    name: str
    qname: str
    ns: tuple[str, ...]
    cls: tuple[str, ...]
    line: int
    end: int
    type: str = ""
    init: str = ""
    doc: str = ""
    bases: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=list)  # enumerators
    access: str = ""
    node: Node | None = None
    init_node: Node | None = None


class CppFile:
    def __init__(self, repo: str, path: str, abspath: Path):
        self.repo, self.path = repo, path
        self.src = abspath.read_bytes()
        self.tree = parser().parse(self.src)
        self.loc = self.src.count(b"\n") + 1
        self.decls: list[Decl] = []
        self.funcs: list[Func] = []
        self._scan()

    # ---- text helpers
    def t(self, node: Node | None) -> str:
        return "" if node is None else self.src[node.start_byte : node.end_byte].decode("utf8", "replace")

    def short(self, node: Node | None, limit: int = 160) -> str:
        s = " ".join(self.t(node).split())
        return s if len(s) <= limit else s[: limit - 1] + "…"

    def string(self, node: Node | None) -> str | None:
        """Value of a string literal node (or concatenation), else None."""
        if node is None:
            return None
        if node.type == "string_literal":
            s = self.t(node)
            i, j = s.find('"'), s.rfind('"')
            return s[i + 1 : j] if 0 <= i < j else None
        if node.type == "concatenated_string":
            parts = [self.string(c) for c in node.named_children]
            return "".join(p for p in parts if p is not None)
        return None

    def includes(self) -> list[tuple[str, int, bool]]:
        out = []
        for m in INCLUDE_RE.finditer(self.src):
            line = self.src.count(b"\n", 0, m.start()) + 1
            out.append((m.group(2).decode(), line, m.group(1) == b"<"))
        return out

    def doc_of(self, node: Node) -> str:
        lines, prev, row = [], node.prev_named_sibling, node.start_point[0]
        while prev is not None and prev.type == "comment" and prev.end_point[0] >= row - 1:
            lines.insert(0, self.t(prev))
            row, prev = prev.start_point[0], prev.prev_named_sibling
        text = "\n".join(lines)
        text = re.sub(r"^\s*(/\*\*?|\*/|\*|///?<?|//!)\s?", "", text, flags=re.M)
        return " ".join(text.replace("*/", " ").split())[:400]

    # ---- scope walk
    def _walk(self, node: Node, ns: tuple, cls: tuple, access: str) -> Iterator[tuple[Node, tuple, tuple, str]]:
        for ch in node.named_children:
            t = ch.type
            if t == "namespace_definition":
                name, body = ch.child_by_field_name("name"), ch.child_by_field_name("body")
                parts = tuple(p for p in self.t(name).split("::") if p) if name else ()
                if body is not None:
                    yield from self._walk(body, ns + parts, cls, access)
            elif t in SCOPE_TYPES:
                yield ch, ns, cls, access
                name, body = ch.child_by_field_name("name"), ch.child_by_field_name("body")
                if body is not None and name is not None:
                    inner = tuple(p for p in strip_template(self.t(name)).split("::") if p)
                    yield from self._walk(body, ns, cls + inner, "private" if t == "class_specifier" else "public")
            elif t == "access_specifier":
                access = self.t(ch).rstrip(":").strip()
            elif t in TRANSPARENT:
                yield from self._walk(ch, ns, cls, access)
            else:
                # `struct X {...} x;` or `typedef struct {...} X;` keep the nested scope visible
                ty = ch.child_by_field_name("type") if t in ("declaration", "field_declaration", "type_definition") else None
                if ty is not None and ty.type in SCOPE_TYPES and ty.child_by_field_name("body") is not None:
                    yield ty, ns, cls, access
                    nm = ty.child_by_field_name("name")
                    if nm is not None:
                        yield from self._walk(ty.child_by_field_name("body"), ns, cls + (self.t(nm),), "public")
                yield ch, ns, cls, access

    @staticmethod
    def _func_declarator(node: Node) -> Node | None:
        d = node.child_by_field_name("declarator")
        while d is not None and d.type != "function_declarator":
            nxt = d.child_by_field_name("declarator")
            if nxt is None:
                kids = [c for c in d.named_children if c.type.endswith("declarator")]
                nxt = kids[-1] if kids else None
            d = nxt
        return d

    @staticmethod
    def _decl_name(d: Node | None) -> Node | None:
        while d is not None and d.type not in ("identifier", "field_identifier", "qualified_identifier", "type_identifier",
                                               "destructor_name", "operator_name", "template_function", "structured_binding_declarator"):
            nxt = d.child_by_field_name("declarator")
            if nxt is None:
                kids = [c for c in d.named_children if c.type.endswith("declarator") or c.type.endswith("identifier")]
                nxt = kids[0] if kids else None
            d = nxt
        return d

    def _scan(self) -> None:
        for node, ns, cls, access in self._walk(self.tree.root_node, (), (), ""):
            t = node.type
            line, end = node.start_point[0] + 1, node.end_point[0] + 1
            if t in SCOPE_TYPES:
                name = node.child_by_field_name("name")
                if name is None or node.child_by_field_name("body") is None:
                    continue
                nm = strip_template(self.t(name))
                bases = []
                for c in node.children:
                    if c.type == "base_class_clause":
                        bases = [strip_template(self.t(b)) for b in c.named_children if b.type in ("type_identifier", "qualified_identifier", "template_type")]
                self.decls.append(Decl("class" if t == "class_specifier" else "struct", nm, "::".join(ns + cls + tuple(nm.split("::"))),
                                       ns, cls, line, end, bases=bases, doc=self.doc_of(node), node=node))
            elif t == "enum_specifier":
                name, body = node.child_by_field_name("name"), node.child_by_field_name("body")
                if body is None:
                    continue
                nm = self.t(name) or "(anonymous)"
                members = [self.t(e.child_by_field_name("name")) for e in body.named_children if e.type == "enumerator"]
                self.decls.append(Decl("enum", nm, "::".join(ns + cls + (nm,)), ns, cls, line, end, members=members, doc=self.doc_of(node), node=node))
            elif t == "function_definition":
                self._add_func(node, ns, cls, access, True)
            elif t in ("declaration", "field_declaration"):
                ty = node.child_by_field_name("type")
                if ty is not None and ty.type == "enum_specifier" and ty.child_by_field_name("body") is not None:
                    nm = self.t(ty.child_by_field_name("name")) or "(anonymous)"
                    members = [self.t(e.child_by_field_name("name")) for e in ty.child_by_field_name("body").named_children if e.type == "enumerator"]
                    self.decls.append(Decl("enum", nm, "::".join(ns + cls + (nm,)), ns, cls, line, end, members=members, doc=self.doc_of(node), node=ty))
                    continue
                if self._func_declarator(node) is not None:
                    self._add_func(node, ns, cls, access, False)
                    continue
                type_text = " ".join(self.t(c) for c in node.children if c.type in ("type_qualifier", "storage_class_specifier")) + " " + self.t(ty)
                for d in node.children_by_field_name("declarator"):
                    init = d.child_by_field_name("value") if d.type == "init_declarator" else None
                    if init is None and t == "field_declaration":
                        init = node.child_by_field_name("default_value")
                    name = self._decl_name(d)
                    if name is None:
                        continue
                    nm = self.t(name)
                    self.decls.append(Decl("field" if cls else "var", nm, "::".join(ns + cls + (nm,)), ns, cls, line, end,
                                           type=" ".join(type_text.split()), init=self.short(init, 240), doc=self.doc_of(node),
                                           access=access, node=node, init_node=init))
            elif t in ("preproc_def", "preproc_function_def"):
                nm = self.t(node.child_by_field_name("name"))
                self.decls.append(Decl("macro", nm, nm, ns, cls, line, end, init=self.short(node.child_by_field_name("value"), 200), node=node))
            elif t in ("alias_declaration", "type_definition"):
                name = node.child_by_field_name("name") or self._decl_name(node.child_by_field_name("declarator"))
                if name is not None:
                    nm = self.t(name)
                    self.decls.append(Decl("alias", nm, "::".join(ns + cls + (nm,)), ns, cls, line, end, type=self.short(node.child_by_field_name("type"), 120), node=node))

    def _add_func(self, node: Node, ns: tuple, cls: tuple, access: str, is_def: bool) -> None:
        fd = self._func_declarator(node)
        if fd is None:
            return
        name_node = fd.child_by_field_name("declarator")
        raw = strip_template(self.t(name_node)) if name_node is not None else "?"
        parts = tuple(p for p in raw.split("::") if p) or ("?",)
        qname = "::".join(ns + cls + parts)
        params: dict[str, str] = {}
        plist = fd.child_by_field_name("parameters")
        if plist is not None:
            for p in plist.named_children:
                if p.type not in ("parameter_declaration", "optional_parameter_declaration"):
                    continue
                pn = self._decl_name(p.child_by_field_name("declarator"))
                if pn is not None:
                    params[self.t(pn)] = self.t(p.child_by_field_name("type"))
        body = node.child_by_field_name("body")
        sig_end = body.start_byte if body is not None else node.end_byte
        sig = " ".join(self.src[node.start_byte:sig_end].decode("utf8", "replace").split()).rstrip(";").strip()
        f = Func(qname, parts[-1], ns, cls + parts[:-1], node.start_point[0] + 1, node.end_point[0] + 1, sig[:300],
                 self.t(node.child_by_field_name("type")), params, self.doc_of(node), node, body, is_def, access)
        if body is not None:
            self._scan_body(f, body, False)
        self.funcs.append(f)

    def _scan_body(self, f: Func, node: Node, in_lambda: bool) -> None:
        for ch in node.named_children:
            t = ch.type
            if t == "declaration":
                ty = self.t(ch.child_by_field_name("type"))
                for d in ch.children_by_field_name("declarator"):
                    init = d.child_by_field_name("value") if d.type == "init_declarator" else None
                    nm = self._decl_name(d)
                    if nm is None:
                        continue
                    tt = ty
                    if ty == "auto" and init is not None:
                        tt = self._infer(init) or "auto"
                    f.locals[self.t(nm)] = tt
                    if init is not None:
                        f.local_init[self.t(nm)] = init
            elif t == "call_expression":
                f.calls.append(self.call(ch, in_lambda))
            self._scan_body(f, ch, in_lambda or t == "lambda_expression")

    def _infer(self, init: Node) -> str | None:
        n = init
        if n.type == "new_expression":
            return self.t(n.child_by_field_name("type"))
        if n.type == "compound_literal_expression":
            return self.t(n.child_by_field_name("type"))
        if n.type == "call_expression":
            fn = n.child_by_field_name("function")
            if fn is not None and fn.type in ("qualified_identifier", "identifier", "template_function"):
                return "call:" + strip_template(self.t(fn))
        return None

    def call(self, node: Node, in_lambda: bool = False) -> Call:
        fn, args = node.child_by_field_name("function"), node.child_by_field_name("arguments")
        name, recv, scope = self.t(fn), None, None
        if fn is not None:
            if fn.type == "field_expression":
                recv, name = self.t(fn.child_by_field_name("argument")), self.t(fn.child_by_field_name("field"))
            elif fn.type == "qualified_identifier":
                scope, _, name = self.t(fn).rpartition("::")
            elif fn.type == "template_function":
                name = self.t(fn.child_by_field_name("name"))
        return Call(strip_template(name), recv, scope, node.start_point[0] + 1, node, list(args.named_children) if args is not None else [], in_lambda)

    def calls_in(self, node: Node) -> Iterator[Call]:
        for ch in node.named_children:
            if ch.type == "call_expression":
                yield self.call(ch)
            yield from self.calls_in(ch)

    def find(self, node: Node, type_: str) -> Iterator[Node]:
        for ch in node.named_children:
            if ch.type == type_:
                yield ch
            yield from self.find(ch, type_)
