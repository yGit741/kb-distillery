"""Render a conversation tree (meta/chats/<id>.json) as one `type: ai-chat` wiki page.

Layout: Chat Summary (a prose summary with inline concept links) → Key concepts →
Visualizations and Branches (indexes that jump into the transcript) → Transcript.
The transcript is ONE collapsible callout. It leads with the main path (the leaf
seen in the most clips); every other branch hangs off its fork point as a nested,
collapsed `[!example]-` callout, so nothing said on any branch is lost. Runnable
html/svg fences become a live sandboxed iframe (dataviewjs) over the extracted asset.
Turn text is read from the raw clips via each node's text_ref — the tree stores
structure, the clips stay the single copy of the words.
"""
import json
import os
import re

from .chat import GEMINI_VISUAL_RE
from .chat_build import main_leaf, path_to
from kb_distillery.vault import frontmatter as fmlib
from .paths import ROOT

ROLE_HEADING = {"user": "#### 🧑 You", "model": "#### ✨ Gemini"}
LABEL_CHARS = 90
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)

IFRAME = '''```dataviewjs
const path = "{path}";
let html = await app.vault.adapter.read(path);
const reporter = "<script>(function(){{var p=function(){{parent.postMessage({{vizHeight:document.documentElement.scrollHeight}},'*');}};new ResizeObserver(p).observe(document.documentElement);addEventListener('load',p);p();}})()</script>";
html = html.includes("</body>") ? html.replace("</body>", reporter + "</body>") : html + reporter;
const frame = dv.container.createEl("iframe");
frame.setAttribute("sandbox", "allow-scripts");
frame.setAttribute("srcdoc", html);
frame.style.width = "100%";
frame.style.height = "760px";  // fallback until first height report
frame.style.border = "1px solid var(--background-modifier-border)";
frame.style.borderRadius = "8px";
const onMsg = (e) => {{
  if (e.source === frame.contentWindow && e.data && e.data.vizHeight)
    frame.style.height = (e.data.vizHeight + 4) + "px";
}};
window.addEventListener("message", onMsg);
```'''

LOST_VISUAL = (
    '> [!warning] <span id="{anchor}"></span>Gemini inline visual — not captured\n'
    "> The clip kept only Gemini's per-session sandbox frame "
    "(`…usercontent.goog/svg-code-block/shim.html`); the visual's code stays in the Gemini chat.")


class Clips:
    def __init__(self, root=ROOT):
        self.root, self._lines = root, {}

    def lines(self, clip):
        if clip not in self._lines:
            with open(os.path.join(self.root, clip), encoding="utf-8") as f:
                self._lines[clip] = f.read().split("\n")
        return self._lines[clip]


class Index:
    """What the transcript contains, in reading order — feeds the lists at the top."""
    def __init__(self, root):
        self.root, self.viz, self.lost, self.branches = root, [], [], []

    def viz_title(self, path):
        try:
            with open(os.path.join(self.root, path), encoding="utf-8") as f:
                m = TITLE_RE.search(f.read(4000))
            return " ".join(m.group(1).split()) if m else "Interactive visualization"
        except OSError:
            return "Interactive visualization"


def turn_markdown(node, clips, index=None):
    """The turn's text from its clip: runnable fences → live iframe, Gemini frames → warning.
    With an `index`, each visual gets an anchor and is recorded for the lists up top."""
    ref = node["text_ref"]
    lines = clips.lines(ref["clip"])
    start, end = ref["start_line"], ref["end_line"]  # 1-indexed, inclusive
    swaps = {f["start_line"]: f for f in node["code_fences"] if f.get("artifact")}
    turn = node["depth"] + 1
    out, i = [], start
    while i <= end and i <= len(lines):
        if i in swaps:
            path = swaps[i]["artifact"]["path"]
            if index is not None:
                k = len(index.viz) + 1
                title = index.viz_title(path)
                index.viz.append({"anchor": f"viz-{k}", "title": title, "turn": turn, "path": path})
                out += [f'<span id="viz-{k}"></span>**▶ Visualization {k} — {title}** · `{path}`', ""]
            out.extend(IFRAME.format(path=path).split("\n"))
            i = swaps[i]["end_line"] + 1
            continue
        line = lines[i - 1]
        if GEMINI_VISUAL_RE.search(line):
            anchor = ""
            if index is not None:
                anchor = f"lost-{len(index.lost) + 1}"
                index.lost.append({"anchor": anchor, "turn": turn})
            out.extend(LOST_VISUAL.format(anchor=anchor).split("\n"))
        else:
            out.append(line)
        i += 1
    while out and not out[-1].strip():
        out.pop()
    if out and out[-1].strip() == "---":
        out.pop()
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def _snippet(conv, nid, clips):
    text = " ".join(turn_markdown(conv["nodes"][nid], clips).split())
    return text[:LABEL_CHARS] + "…" if len(text) > LABEL_CHARS else text


def _label(conv, nid, clips):
    if conv["nodes"][nid]["role"] == "model":
        return "alternative answer"
    return "“" + _snippet(conv, nid, clips) + "”"


def _branch_leaf(conv, nid):
    """Within a side branch, follow the child seen in most clips (deepest on ties)."""
    nodes = conv["nodes"]
    while nodes[nid]["children"]:
        nid = max(nodes[nid]["children"],
                  key=lambda c: (len(nodes[c]["seen_in"]), _depth_below(nodes, c), c))
    return nid


def _depth_below(nodes, nid):
    best, stack = 0, [(nid, 0)]
    while stack:
        cur, d = stack.pop()
        best = max(best, d)
        stack.extend((c, d + 1) for c in nodes[cur]["children"])
    return best


def _quote(text):
    return "\n".join("> " + l if l else ">" for l in text.split("\n"))


def render_path(conv, path, clips, index, level=0):
    """Blocks for a root-to-leaf path; forks off it become collapsed callouts."""
    nodes, blocks = conv["nodes"], []
    on_path = set(path)
    for nid in path:
        n = nodes[nid]
        parent = nodes.get(n["parent"]) if n["parent"] else None
        resume = (f'<span id="main-after-{parent["depth"] + 1}"></span>'
                  if level == 0 and parent and len(parent["children"]) > 1 else "")
        blocks.append(f"{resume}{ROLE_HEADING[n['role']]} · turn {n['depth'] + 1}\n\n"
                      f"{turn_markdown(n, clips, index)}")
        side = [c for c in n["children"] if c not in on_path]
        for k, child in enumerate(side, 1):
            sub = path_to(conv, _branch_leaf(conv, child))
            sub = sub[sub.index(child):]
            b = {"anchor": f"branch-{len(index.branches) + 1}", "after": n["depth"] + 1,
                 "label": _label(conv, child, clips), "turns": len(sub), "level": level}
            index.branches.append(b)
            body = "\n\n---\n\n".join(render_path(conv, sub, clips, index, level + 1))
            head = (f'> [!example]- <span id="{b["anchor"]}"></span>⑂ Branch {k}/{len(side)} '
                    f'after turn {b["after"]} — {b["label"]} · {b["turns"]} '
                    f'turn{"s" if b["turns"] != 1 else ""}')
            blocks.append(head + "\n" + _quote(body))
    return blocks


def stats(conv):
    nodes = conv["nodes"].values()
    fences = [f for n in nodes for f in n["code_fences"]]
    arts = {f["artifact"]["path"] for f in fences if f.get("artifact")}
    return {"turns": len(conv["nodes"]), "branches": len(conv["leaves"]),
            "visualizations": len(arts), "code": len(fences),
            "lost": sum(n.get("inline_visuals", 0) for n in nodes)}


def frontmatter(conv, title, aliases=(), extra=None):
    q = lambda s: json.dumps(s, ensure_ascii=False)
    lines = ["---", "type: ai-chat", "layer: source", "maturity: to-read", "status: draft", "depth: listed"]
    if fmlib.title_line(title):                    # only when it differs from the `# ` heading it is written with
        lines.insert(3, f"title: {q(title)}")
    if aliases:
        lines.append(f"aliases: [{', '.join(q(a) for a in aliases)}]")
    lines += [f"provider: {conv['provider']}",
              f"raw: {conv['canonical_clip']}",
              f"conversation: {conv['id']}",
              f"clips: [{', '.join(sorted(conv['clips']))}]"]
    if conv["source_urls"]:
        lines.append(f"url: {conv['source_urls'][0]}")
    for k, v in (extra or {}).items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def _viz_section(index):
    if not index.viz and not index.lost:
        return "_No visualizations in this chat._"
    out = [f"- [{v['title']}](#{v['anchor']}) — interactive, turn {v['turn']}" for v in index.viz]
    out += [f"- [Gemini inline visual](#{x['anchor']}) — turn {x['turn']}, not captured by the clipper"
            for x in index.lost]
    return "\n".join(out)


def _branch_section(conv, main, clips, index):
    if not index.branches:
        return "_A single thread — no branches._"
    nodes = conv["nodes"]
    fork_children = {b["after"] for b in index.branches if b["level"] == 0}
    # where the main path leaves each top-level fork, so the reader sees what it chose
    lines = []
    for nid in main:
        n = nodes[nid]
        if n["depth"] + 1 in fork_children and len(n["children"]) > 1:
            nxt = next(c for c in n["children"] if c in set(main))
            lines.append(f"- [**Main path** after turn {n['depth'] + 1}](#main-after-{n['depth'] + 1}) — "
                         f"{_label(conv, nxt, clips)} · turns {n['depth'] + 2}–{len(main)}")
    for b in index.branches:
        pad = "  " * (b["level"] + (1 if b["level"] else 0))
        lines.append(f"{pad}- [⑂ Branch after turn {b['after']}](#{b['anchor']}) — {b['label']} · "
                     f"{b['turns']} turn{'s' if b['turns'] != 1 else ''}")
    return "\n".join(lines)


def render(conv, title, aliases=(), sections=None, root=ROOT, extra=None):
    """Full page markdown. `sections` keeps hand-written Chat Summary / Key concepts."""
    clips, index = Clips(root), Index(root)
    s = stats(conv)
    sections = sections or {}
    main = path_to(conv, main_leaf(conv))
    body = "\n\n---\n\n".join(render_path(conv, main, clips, index))

    summary = (f"{len(main)} turns on the main path · {s['turns']} in all"
               + (f" · {s['branches']} branches" if s["branches"] > 1 else "")
               + f" · {s['visualizations']} visualization(s)"
               + (f" · {s['lost']} not captured" if s["lost"] else ""))
    provenance = "\n".join([
        "> [!info]- Provenance",
        f"> - Source: {conv['source_urls'][0] if conv['source_urls'] else '(none recorded)'}",
        *[f"> - Clip: `{c}`" for c in sorted(conv["clips"])],
        f"> - Tree: `meta/chats/{conv['id']}.json`",
    ])
    page = [
        frontmatter(conv, title, aliases, extra), "", f"# {title}", "",
        "## Chat Summary", "", sections.get("Chat Summary", ""), "",
        "## Key concepts", "", sections.get("Key concepts", ""), "",
        "## Visualizations", "", _viz_section(index), "",
        "## Branches", "", _branch_section(conv, main, clips, index), "",
        "## Transcript", "", provenance, "",
        f"> [!quote]+ Transcript — {summary}",
        _quote(body), "",
    ]
    text = "\n".join(page)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text
