"""IR cards: deterministic markdown views of the IR graph, one per entity or question a wiki page needs to cite.

A card is a set of fact tables. Every row is one fact: an id (stable within the card), what it says, the IR layer and
confidence it comes from, and an anchor (`path:line` at the pinned commit, linked to the repository host). Nothing in a
card is written by a model, so a card can be regenerated at any commit and diffed.

Cards any repo gets: classes by folder, Python modules, change history, includes.
    distill code cards <project>      # writes <out>/cards/*.md + <out>/cards/index.json
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from kb_distillery.codekb.generic.graph import Graph
from kb_distillery.codekb.generic.project import Project


class Card:
    def __init__(self, g: Graph, p: Project, slug: str, title: str, layers: list[str], what: str, repo: str = ""):
        self.g, self.p, self.slug, self.title, self.layers, self.what, self.repo = g, p, slug, title, layers, what, repo
        self.parts: list[str] = []
        self.n = 0
        self.facts: list[dict] = []
        self.ids: set[str] = set()
        self.section = ""
        self.repos_used: set[str] = set()

    # -- anchors -------------------------------------------------------------------------------------------------
    def a(self, repo: str | None, path: str | None, line: int | None, end: int | None = None) -> str:
        if not repo or not path:
            return ""
        sha = self.g.meta["repos"][repo]["sha"]
        label = f"{path}:{line}" if line else path
        if repo != self.repo:
            label = f"{repo}:{label}"
        self.repos_used.add(repo)
        url = self.p.permalink(repo, sha, path, line, end)
        return f"[`{label}`]({url})" if url else f"`{label}`"

    def ae(self, e: dict) -> str:
        return self.a(e.get("repo"), e.get("path"), e.get("line"))

    def an(self, nid: str) -> str:
        n = self.g.nodes.get(nid, {})
        return self.a(n.get("repo"), n.get("path"), n.get("line"))

    # -- content -------------------------------------------------------------------------------------------------
    def h(self, heading: str, note: str = "") -> None:
        self.section = heading
        self.parts.append(f"\n## {heading}\n")
        if note:
            self.parts.append(note + "\n")

    def text(self, s: str) -> None:
        self.parts.append(s + "\n")

    def table(self, cols: list[str], rows: list[list], anchors: list[list[dict]] | None = None) -> None:
        """Each row is one fact. Its id is a hash of what it says (section + cells, line numbers and links removed), so the id
        survives a rebuild at another commit as long as the fact itself still holds, and disappears when it does not."""
        if not rows:
            self.parts.append("_No facts in this layer._\n")
            return
        out = ["| # | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
        for r in rows:
            self.n += 1
            cells = [str(c).replace("|", "\\|").replace("\n", " ") for c in r]
            links = re.findall(r"\]\((https?://[^)]+)\)", " ".join(cells))
            plain = re.sub(r"\[(`[^`]+`)\]\([^)]+\)", r"\1", " · ".join(cells))
            key = self.section + "|" + re.sub(r"`([^`]*?):\d+`", r"`\1`", plain)
            fid = "F" + hashlib.sha1(key.encode()).hexdigest()[:5]
            while fid in self.ids:
                fid += "x"
            self.ids.add(fid)
            out.append(f"| {fid} | " + " | ".join(cells) + " |")
            self.facts.append({"id": fid, "section": self.section, "text": plain, "anchors": links})
        self.parts.append("\n".join(out) + "\n")

    def render(self) -> str:
        meta = self.g.meta
        repos = sorted(self.repos_used)
        fm = ["---", "source: ir", f'id: "{self.slug}"', f'title: "{self.title}"', f"ir_layers: [{', '.join(self.layers)}]",
              f'generator: "{meta["generator"]}"', "pinned:"]
        fm += [f'  {r}: "{meta["repos"][r]["sha"]}"' for r in repos]
        fm += [f"facts: {self.n}", "---", "", f"# {self.title}", "", self.what, "",
               "Every row is one deterministic fact extracted from the code at the pinned commits above. `conf` says how the fact was "
               "resolved (see the legend at the end). Anchors link to the exact line on the repository host.", ""]
        legend = ("\n## Confidence legend\n\n`exact` literal in the code at the anchor · `typed` receiver type resolved through declarations · "
                  "`name-unique` only one symbol of that name exists · `import` resolved through the file's imports · "
                  "`observed` counted from the history · `external` points outside the indexed repositories · "
                  "`syntactic` text only, unresolved.\n")
        return "\n".join(fm) + "\n".join(self.parts) + legend


def short(nid: str) -> str:
    return nid.split(":", 1)[1] if ":" in nid else nid


def code(s: str) -> str:
    return f"`{s}`"


class Cards:
    def __init__(self, g: Graph, p: Project):
        self.g, self.p = g, p
        self.out: dict[str, Card] = {}
        self.by_src: dict[str, list[dict]] = defaultdict(list)
        self.by_dst: dict[str, list[dict]] = defaultdict(list)
        for e in g.edges:
            self.by_src[e["src"]].append(e)
            self.by_dst[e["dst"]].append(e)

    def E(self, layer: str | None = None, kind: str | None = None, src: str | None = None, dst: str | None = None, repo: str | None = None):
        pool = self.by_src[src] if src else self.by_dst[dst] if dst else self.g.edges
        return [e for e in pool if (not layer or e["layer"] == layer) and (not kind or e["kind"] == kind) and (not dst or e["dst"] == dst)
                and (not repo or e.get("repo") == repo)]

    def card(self, slug, title, layers, what, repo="") -> Card:
        c = Card(self.g, self.p, slug, title, layers, what, repo)
        self.out[slug] = c
        return c

    def name(self, nid: str) -> str:
        n = self.g.nodes.get(nid)
        return n["name"] if n else short(nid)

    def classes(self, slug: str, title: str, classes: list[str], what: str, repo: str = "", layers=None, methods_cap: int = 40) -> None:
        g = self.g
        c = self.card(slug, title, layers or ["symbol", "call", "config", "history"], what, repo)
        cids = [f"class:{q}" for q in classes if f"class:{q}" in g.nodes]
        funcs = {n["id"]: n for n in g.nodes.values() if n["kind"] in ("method", "function") and n.get("cls") in classes}
        files = sorted({(n["repo"], n["path"]) for n in list(funcs.values()) + [g.nodes[x] for x in cids]})

        c.h("Classes and files")
        rows = []
        for cid in cids:
            n = g.nodes[cid]
            inh = ", ".join(code(self.name(e["dst"])) for e in self.E("symbol", "inherits", src=cid)) or "none"
            mem = self.E("symbol", "has_member", src=cid)
            rows.append([code(n["name"]), n["kind"], inh, n.get("n_methods", 0), n.get("n_fields", 0),
                         ", ".join(f'`{e.get("via")}`: {code(self.name(e["dst"]).split("::")[-1])}' for e in mem[:12]), c.an(cid)])
        c.table(["Class", "Kind", "Bases", "Methods", "Fields", "Members that are classes", "Anchor"], rows)
        c.table(["File", "Role"], [[c.a(r, p, None), "implementation" if p.endswith((".cpp", ".cc")) else "declaration"] for r, p in files])

        c.h("Methods", "Declarations in source order; the doc column is the comment above the declaration, verbatim, cut at 160 characters.")
        rows = []
        for cid in cids:
            decl = sorted((n for n in funcs.values() if n["cls"] == short(cid) and not n.get("defined") or n["cls"] == short(cid) and n["path"].endswith((".h", ".hpp"))),
                          key=lambda n: (n["path"], n["line"]))
            seen = set()
            for n in decl:
                if n["name"] in seen or len(seen) >= methods_cap:
                    continue
                seen.add(n["name"])
                sig = re.sub(r"\s+", " ", n.get("sig", ""))[:150]
                rows.append([code(sig), n.get("access", ""), (n.get("doc") or "")[:160], c.an(n["id"])])
        c.table(["Signature", "Access", "Doc comment", "Anchor"], rows)

        c.h("Calls out", "Calls from these classes into other classes or free functions (the call layer resolves a call when the receiver type is known).")
        agg: dict[tuple, list[dict]] = defaultdict(list)
        for fid in funcs:
            for e in self.E("call", "calls", src=fid):
                d = g.nodes.get(e["dst"], {})
                if d.get("cls") not in classes:
                    agg[(funcs[fid]["name"], d.get("name", short(e["dst"])))].append(e)
        rows = [[code(s.split("::", 1)[-1]), code(d), len(es), ", ".join(sorted({e["conf"] for e in es})), c.ae(es[0])] for (s, d), es in sorted(agg.items())]
        c.table(["Caller", "Callee", "Calls", "conf", "First anchor"], rows[:80])
        if len(rows) > 80:
            c.text(f"_{len(rows) - 80} more call rows are in the IR database._")

        c.h("Called by")
        agg = defaultdict(list)
        for fid in funcs:
            for e in self.E("call", "calls", dst=fid):
                s = g.nodes.get(e["src"], {})
                if s.get("cls") not in classes:
                    agg[(s.get("name", short(e["src"])), funcs[fid]["name"])].append(e)
        rows = [[code(s), code(d.split("::", 1)[-1]), len(es), ", ".join(sorted({e["conf"] for e in es})), c.ae(es[0])] for (s, d), es in sorted(agg.items())]
        c.table(["Caller", "Method", "Calls", "conf", "First anchor"], rows[:60])

        cfg = []
        for fid in funcs:
            for e in self.by_src[fid]:
                if e["layer"] == "config":
                    cfg.append([code(funcs[fid]["name"].split("::", 1)[-1]), e["kind"].replace("_", " "), code(self.name(e["dst"])), c.ae(e)])
        if cfg:
            c.h("Configuration touched")
            c.table(["Where", "Relation", "Target", "Anchor"], cfg[:60])

        hist = self.history_rows(c, [f"file:{r}:{p}" for r, p in files])
        if hist:
            c.h("Change history", "Merge requests that touched these files, newest first, and the files that most often change in the same merge request.")
            c.table(["MR", "Date", "Author", "Title or branch", "Files of this card touched"], hist[0])
            if hist[1]:
                c.table(["File here", "Changes together with", "Shared MRs", "Jaccard"], hist[1])

    def history_rows(self, c: Card, fids: list[str]):
        g = self.g
        mrs: dict[str, int] = Counter()
        for f in fids:
            for e in self.E("history", "touches", dst=f):
                mrs[e["src"]] += 1
        if not mrs:
            return None
        a = []
        for m, k in sorted(mrs.items(), key=lambda kv: g.nodes[kv[0]].get("date", ""), reverse=True)[:15]:
            n = g.nodes[m]
            url = n.get("url") or ""
            a.append([f'[!{n.get("iid")}]({url})' if url else f'!{n.get("iid")}', n.get("date", ""), n.get("author", ""), (n.get("title") or n.get("source_branch") or "")[:90], k])
        b = []
        inside = set(fids)
        for f in fids:
            for e in self.E("history", "cochange", src=f) + self.E("history", "cochange", dst=f):
                o = e["dst"] if e["src"] == f else e["src"]
                if o not in inside and e.get("n", 0) >= 3:
                    b.append((e["n"], e.get("jaccard", 0), g.nodes[f]["path"], g.nodes[o]["path"]))
        b = [[code(x[2]), code(x[3]), x[0], x[1]] for x in sorted(b, reverse=True)[:12]]
        return a, b

    def history(self, repo: str) -> None:
        g, name = self.g, self.p.display(repo)
        c = self.card(f"ir-history-{slug_of(repo)}", f"IR: {name} change history", ["history"],
                      f"Who changed what in `{repo}`, by merge request, and which files change together. Co-change counts use feature merge requests "
                      "that touch 2 to 25 code files, so that bulk moves do not dominate.", repo)
        mrs = sorted((n for n in g.nodes.values() if n["kind"] == "merge-request" and n.get("repo") == repo), key=lambda n: n.get("date", ""))
        if not mrs:
            self.history_by_commit(c, repo)
            return
        c.h("Merge requests", "Merged pull requests and merge requests, found from the first-parent merge commits.")
        rows = []
        for n in mrs:
            url = n.get("url") or ""
            rows.append([f'[!{n.get("iid")}]({url})' if url else f'!{n.get("iid")}', n.get("date", ""), n.get("author", ""), (n.get("title") or n.get("source_branch") or "")[:100],
                         len(self.E("history", "touches", src=n["id"]))])
        c.table(["MR", "Merged", "Author", "Title or branch", "Files"], rows)
        c.h("Authors")
        au = Counter(n.get("author", "?") for n in mrs)
        c.table(["Author", "Merge requests"], [[a, k] for a, k in au.most_common()])
        c.h("Files that change together")
        mine = lambda nid: g.nodes.get(nid, {}).get("repo") == repo  # noqa: E731
        co = sorted((e for e in self.E("history", "cochange") if mine(e["src"])), key=lambda e: (-e.get("n", 0), -e.get("jaccard", 0)))[:40]
        c.table(["File A", "File B", "Shared MRs", "Jaccard"], [[code(g.nodes[e["src"]]["path"]), code(g.nodes[e["dst"]]["path"]), e["n"], e["jaccard"]] for e in co])
        c.h("Most changed files")
        ch = Counter()
        for e in self.E("history", "touches", repo=repo):
            ch[e["dst"]] += 1
        c.table(["File", "Merge requests"], [[c.a(repo, g.nodes[f]["path"], None), k] for f, k in ch.most_common(25)])
        o = g.nodes.get(f"owners:{repo}")
        if o:
            c.h("Code owners")
            c.table(["Pattern", "Owners", "Anchor"], [[code(r["pattern"]), ", ".join(r["owners"]), c.a(repo, o["path"], r["line"])] for r in o.get("rules", [])
                                                      if not r["pattern"].startswith("[")])

    def history_by_commit(self, c: Card, repo: str) -> None:
        """A repo with no merge commits (fast-forward or squash merges): the same questions answered per commit."""
        g = self.g
        h = (g.meta.get("history") or {}).get(repo) or {}
        c.text(f"No merge commit was found in `{repo}`, so a commit is the unit of change here ({h.get('commits', 0)} commits).")
        c.h("Authors")
        c.table(["Author", "Commits"], [[a, k] for a, k in h.get("authors", [])])
        c.h("Files that change together", "Pairs of files changed in the same commit, for commits that touch 2 to 25 code files.")
        mine = lambda nid: g.nodes.get(nid, {}).get("repo") == repo  # noqa: E731
        co = sorted((e for e in self.E("history", "cochange") if mine(e["src"])), key=lambda e: (-e.get("n", 0), -e.get("jaccard", 0), e["src"], e["dst"]))[:40]
        c.table(["File A", "File B", "Shared commits", "Jaccard"], [[code(g.nodes[e["src"]]["path"]), code(g.nodes[e["dst"]]["path"]), e["n"], e["jaccard"]] for e in co])
        c.h("Most changed files")
        files = sorted((n for n in g.nodes.values() if n["kind"] == "file" and n.get("repo") == repo and n.get("n_commits")),
                       key=lambda n: (-n["n_commits"], n["path"]))[:25]
        c.table(["File", "Commits", "Authors", "Last change"], [[c.a(repo, n["path"], None), n["n_commits"], ", ".join(n.get("authors", [])), n.get("last_change", "")] for n in files])

    def includes(self, repo: str) -> None:
        g, name = self.g, self.p.display(repo)
        c = self.card(f"ir-includes-{slug_of(repo)}", f"IR: what {name} includes from other repositories", ["include"],
                      f"Compile-time dependencies of `{repo}` on other repositories, from `#include` lines. Headers that resolve inside one of the "
                      f"{len(self.p.repos)} indexed repositories are listed with their target; the rest are counted as external.", repo)
        per: dict[str, list[dict]] = defaultdict(list)
        ext: Counter = Counter()
        for e in self.E("include", "includes", repo=repo):
            d = g.nodes.get(e["dst"], {})
            if d.get("kind") == "file" and d.get("repo") != repo:
                per[d["repo"]].append(e)
            elif d.get("kind") == "external-header":
                ext[d["name"]] += 1
        c.h("Resolved cross-repository includes")
        rows = []
        for r, es in sorted(per.items()):
            hd: dict[str, list[dict]] = defaultdict(list)
            for e in es:
                hd[g.nodes[e["dst"]]["path"]].append(e)
            for h, xs in sorted(hd.items()):
                rows.append([r, code(h), len(xs), "; ".join(c.ae(x) for x in xs[:3])])
        c.table(["Repository", "Header", "Includers", "Included at"], rows)
        c.h("External headers", "Headers outside the indexed repositories (system and third-party).")
        c.table(["Header", "Includers"], [[code(h), k] for h, k in ext.most_common(40)])
        c.h(f"Who includes {name}", f"Files in the other indexed repositories that include a {name} header.")
        rows = []
        for e in self.E("include", "includes"):
            d = g.nodes.get(e["dst"], {})
            if d.get("repo") == repo and e.get("repo") != repo:
                rows.append([code(f'{e["repo"]}:{e["path"]}'), code(d["path"]), c.ae(e)])
        c.table(["Includer", f"{name} header", "Anchor"], rows)

    # ------------------------------------------------------------------------------------------------------------
    def class_groups(self, repo: str, taken: set[str]) -> list[tuple[str, str, list[str]]]:
        """Classes of a repo that no other card covers, one group per top-level folder: (slug, title, classes)."""
        by_dir: dict[str, list[str]] = defaultdict(list)
        for n in self.g.nodes.values():
            if n.get("repo") == repo and n["kind"] in ("class", "struct") and n.get("lang") != "python" and n["name"] not in taken:
                top = n["path"].split("/")[0] if "/" in n["path"] else "(root)"
                by_dir[top].append(n["name"])
        name = self.p.display(repo)
        return [(f"ir-{slug_of(repo)}-dir-{slug_of(d)}", f"IR: {name} folder {d}/", sorted(cl)) for d, cl in sorted(by_dir.items())]

    def generic_cards(self, repo: str, taken: set[str]) -> None:
        """Cards any C++ focus repo gets: one per folder for the classes no domain card took, plus history and includes."""
        for slug, title, cl in self.class_groups(repo, taken):
            self.classes(slug, title, cl, f"The classes declared under this folder of `{repo}`: their methods, calls, configuration and change history.", repo)
        self.python_modules(repo)
        if self.p.repo(repo).git:
            self.history(repo)
        if any(n["kind"] == "file" and n.get("repo") == repo and n.get("lang") == "cpp" for n in self.g.nodes.values()):
            self.includes(repo)

    def python_modules(self, repo: str) -> None:
        """One card per top-level folder of a repo's Python files: the modules, their functions, what imports and calls
        what, which scripts name other scripts, and the options and environment variables they read."""
        g, name = self.g, self.p.display(repo)
        by_dir: dict[str, list[dict]] = defaultdict(list)
        for n in g.nodes.values():
            if n["kind"] == "file" and n.get("repo") == repo and n.get("lang") == "python":
                by_dir[n["path"].split("/")[0] if "/" in n["path"] else "(root)"].append(n)
        for d, files in sorted(by_dir.items()):
            files.sort(key=lambda n: n["path"])
            ids = {n["id"] for n in files}
            c = self.card(f"ir-{slug_of(repo)}-py-{slug_of(d)}", f"IR: {name} Python modules in {d}/", ["symbol", "include", "call", "config"],
                          f"The Python files under `{d}/` of `{repo}`: what each defines, imports, calls and starts, read with the `ast` module "
                          "(nothing is imported or run).", repo)
            defs: dict[str, list[dict]] = defaultdict(list)
            for f in files:
                for e in self.E("symbol", "defines", src=f["id"]):
                    defs[f["id"]].append(g.nodes[e["dst"]])
            c.h("Modules")
            c.table(["File", "Lines", "Run as a script", "Classes", "Functions"],
                    [[c.a(repo, f["path"], None), f.get("loc", ""), "yes" if f.get("entry") else "",
                      ", ".join(code(x["name"].split(".")[-1]) for x in defs[f["id"]] if x["kind"] == "class")[:200],
                      sum(1 for x in defs[f["id"]] if x["kind"] == "function")] for f in files])
            c.h("Functions", "Module-level functions in source order; the doc column is the first paragraph of the docstring.")
            rows = [[code(re.sub(r"\s+", " ", x.get("sig", x["name"]))[:150]), code(f["path"]), (x.get("doc") or "")[:160], c.an(x["id"])]
                    for f in files for x in sorted(defs[f["id"]], key=lambda x: x.get("line", 0)) if x["kind"] == "function"]
            c.table(["Signature", "File", "Docstring", "Anchor"], rows[:250])
            if len(rows) > 250:
                c.text(f"_{len(rows) - 250} more functions are in the IR database._")
            c.h("Imports", "Imports that resolve to another indexed file.")
            c.table(["File", "Imports", "Anchor"], [[code(f["path"]), code(self._where(repo, g.nodes[e["dst"]])), c.ae(e)]
                                                    for f in files for e in self.E("include", "includes", src=f["id"]) if g.nodes[e["dst"]]["kind"] == "file"])
            ext: Counter = Counter()
            for f in files:
                for e in self.E("include", "includes", src=f["id"]):
                    if g.nodes[e["dst"]]["kind"] == "external-module":
                        ext[g.nodes[e["dst"]]["name"]] += 1
            c.h("External packages", "Imported packages that are neither in the indexed repositories nor in the standard library.")
            c.table(["Package", "Importing files"], [[code(k), v] for k, v in ext.most_common(40)])
            c.h("Calls into other modules", "A call is listed when its target resolves through the module's imports, `self.`, or a name only one function has.")
            agg: dict[tuple, list[dict]] = defaultdict(list)
            for f in files:
                for x in defs[f["id"]]:
                    if x["kind"] not in ("function", "method"):
                        continue
                    for e in self.E("call", "calls", src=x["id"]):
                        t = g.nodes.get(e["dst"], {})
                        if t.get("path") and (t.get("repo"), t["path"]) != (repo, f["path"]):
                            agg[(x["name"], t["name"])].append(e)
            rows = [[code(s), code(t), len(es), ", ".join(sorted({e["conf"] for e in es})), c.ae(es[0])] for (s, t), es in sorted(agg.items())]
            c.table(["Caller", "Callee", "Calls", "conf", "First anchor"], rows[:120])
            c.h("Scripts named by a script", "A string in the file names another indexed script: the file starts it (subprocess, os.system) or documents it.")
            runs: dict[tuple, list[dict]] = defaultdict(list)
            for f in files:
                for e in self.E("call", "runs", src=f["id"]):
                    runs[(f["path"], self._where(repo, g.nodes[e["dst"]]))].append(e)
            c.table(["File", "Names", "Mentions", "First anchor"], [[code(s), code(t), len(es), c.ae(es[0])] for (s, t), es in sorted(runs.items())])
            opts, envs = [], []
            for f in files:
                srcs = [f["id"]] + [e["dst"] for e in self.by_src.get(f["id"], []) if e["layer"] == "symbol"]
                for s in srcs:
                    for e in self.by_src.get(s, []):
                        if e["layer"] != "config":
                            continue
                        t = g.nodes[e["dst"]]
                        if t["kind"] == "flag":
                            opts.append([code(t["name"]), ", ".join(code(x) for x in t.get("aliases", [])), code(t["default"]) if t.get("default") else "",
                                         t.get("doc", ""), c.ae(e)])
                        elif t["kind"] == "env-var":
                            envs.append([code(t["name"]), code(f["path"]), c.ae(e)])
            c.h("Command-line options")
            c.table(["Option", "Aliases", "Default", "Help", "Anchor"], opts[:200])
            c.h("Environment variables read")
            c.table(["Variable", "File", "Anchor"], envs[:120])

    @staticmethod
    def _where(repo: str, n: dict) -> str:
        return n["path"] if n.get("repo") == repo else f'{n.get("repo")}:{n["path"]}'


def build_cards(g: Graph, p: Project) -> dict[str, "Card"]:
    """Per focus repo: its classes by folder, its Python modules, its history and its cross-repository includes."""
    cs = Cards(g, p)
    for r in p.focus:
        cs.generic_cards(r.name, set())
    return cs.out


def slug_of(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "root"


def write_cards(cards: dict[str, "Card"], out: Path) -> list[dict]:
    d = out / "cards"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.md"):
        f.unlink()
    index = []
    for slug, c in sorted(cards.items()):
        text = c.render()
        (d / f"{slug}.md").write_text(text)
        index.append({"slug": slug, "title": c.title, "layers": c.layers, "what": c.what, "facts": c.n, "chars": len(text), "repo": c.repo,
                      "fact_list": c.facts})
    (d / "index.json").write_text(json.dumps(index, indent=1))
    return index
