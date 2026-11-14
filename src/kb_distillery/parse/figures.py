"""Figures of a transcribed page: cut from the page image, linked from the transcript, described once by a model.

The reader writes a figure as the line `![](figure)` (it never transcribes what is drawn inside one) and the parser
gives the box of every image region. They are paired in reading order; each figure becomes

    ![Figure 1.1](figure:<sha12>/p0028/1)

in the page's Markdown, a PNG `figures/p0028-1.png` beside the page JSON and a record in its `figures` list:
`{id, label, caption, box, file, description, problem}`. `problem` says why a figure is not trustworthy as it stands
(no region found, so the crop is the whole page; a region the reader did not place). A figure with a problem also
gets a `!!` page mark so it is looked at, like any other place one voice decided.

The description is one `kb_distillery.llm` request per figure, with its crop and caption: what the figure shows, in
words and LaTeX, so a digest (and a reader of the page) can use what is drawn, not just the caption. It is cached per
figure under the work dir; the backend is the usual `--backend` choice.
"""
from __future__ import annotations

import json
import os
import re

PLACEHOLDER = re.compile(r"!\[[^\]\n]*\]\((?:figure|image)\)")
LINK = re.compile(r"!\[([^\]\n]*)\]\(figure:([0-9a-f]{12})/p(\d{4})/(\d+)\)")
CAPTION = re.compile(r"^\s*(?:\*\*|\*|_)?\s*((?:Figure|Fig\.|FIGURE)\s*[0-9A-Z][0-9A-Za-z.\-]*?)"
                     r"(?:\.?(?:\*\*|\*|_)[:.]?|[:.])\s")      # a separator after the number: "Figure 3 shows" is prose
MAX_CAPTION = 800
MARK_LINK = re.compile(r"\s?\[!!?\]\(mark:[^)]*\)")
MIN_SIDE = 0.04             # a parser region narrower or shorter than this share of the page is a glyph, not a figure
PAD = 0.008
FIG_WIDTH = 2400            # page render width for figure crops: a figure is read, not glanced at
DESCRIBE_MAX_TOKENS = 1500
USD_PER_FIGURE = {"subscription": 0.0, "api": 0.02, "batch": 0.01}

DESCRIBE_PROMPT = """The image is one figure from a page of a mathematics or machine-learning book.
Caption printed under it (may be empty): {caption}

Describe what the figure shows so that someone who cannot see it can use it: what kind of figure it is (plot, diagram,
tree, graph, table-like drawing...), its axes with labels and ranges, the curves, shapes, nodes and edges, every label or
formula written inside it (in LaTeX, $...$), and what it illustrates. Describe only what is visible; do not explain
the mathematics beyond that. Two to eight sentences, plain prose, no heading, no list.

Write the description, and nothing else, between a line `<<<FIGURE` and a line `FIGURE>>>`."""
REPLY = re.compile(r"^[ \t]*<<<FIGURE[ \t]*\n(.*?)^[ \t]*FIGURE>>>[ \t]*$", re.S | re.M)


def reply_text(text: str) -> str | None:
    """The description between the markers; None when they are missing (a remark of the model's own is not one)."""
    m = REPLY.search((text or "").replace("\r\n", "\n"))
    return " ".join(m.group(1).split()) if m and m.group(1).strip() else None


def regions(boxes: list) -> list:
    """The parser's image regions that are figures (fractions of the page), in reading order; glyph-sized ones dropped."""
    return [list(b) for b in boxes if b and (b[2] - b[0]) >= MIN_SIDE and (b[3] - b[1]) >= MIN_SIDE]


def link(label: str, sha: str, page: int, n: int) -> str:
    return "![%s](figure:%s/p%04d/%d)" % (label.replace("]", ")").replace("[", "("), sha[:12], page, n)


def _caption_near(md: str, start: int, end: int, taken: int = 0) -> tuple:
    """(label, caption) of the caption paragraph right after a figure, else right before it (unless that paragraph lies
    before `taken`: an earlier figure's caption), else ("", ""). Placeholders and mark links are left out."""
    rest = md[end:].lstrip("\n")
    after = rest.split("\n\n", 1)[0]
    after = PLACEHOLDER.split(after, 1)[0].strip()
    head = md[:start].rstrip("\n")
    cut = head.rfind("\n\n")
    before = head[cut + 2:].strip() if cut + 2 >= taken else ""
    for para, stop in ((after, end + (len(md[end:]) - len(rest)) + len(after)), (before, start)):
        m = CAPTION.match(para + " ") if para and len(para) <= MAX_CAPTION else None
        if m:
            return m.group(1).strip(), MARK_LINK.sub("", para).strip(), stop
    return "", "", 0


def place(md: str, boxes: list, sha: str, page: int) -> tuple:
    """(Markdown with figure links, [figure records]) for one page. `boxes`: the parser's figure regions in reading order.
    Placeholders and regions are paired in order; a placeholder without a region keeps the whole page as its crop, a
    region without a placeholder is added at the end of the page. Both carry a `problem`."""
    regs = regions(boxes)
    found = list(PLACEHOLDER.finditer(md))
    figs, out, pos, taken = [], [], 0, 0
    for i, m in enumerate(found):
        n = i + 1
        label, caption, stop = _caption_near(md, m.start(), m.end(), taken)
        taken = max(taken, stop, m.end())
        box = regs[i] if i < len(regs) else None
        problem = "" if box else "the parser found no figure region here: the crop is the whole page"
        figs.append({"id": n, "label": label, "caption": caption, "box": box, "file": "", "description": "",
                     "problem": problem})
        out.append(md[pos:m.start()])
        out.append(link(label or "Figure", sha, page, n))
        pos = m.end()
    out.append(md[pos:])
    text = "".join(out)
    for j, box in enumerate(regs[len(found):], len(found) + 1):
        figs.append({"id": j, "label": "", "caption": "", "box": box, "file": "", "description": "",
                     "problem": "the reader did not place this figure: it is shown at the end of the page, not where "
                                "it stands in the text"})
        text = text.rstrip("\n") + "\n\n" + link("Figure", sha, page, j) + "\n"
    return text, figs


def write_crops(pdf: str, page: int, figs: list, root: str, sha: str) -> None:
    """One PNG per figure under `<root>/<sha>/figures/` (the whole page when it has no box); sets each record's `file`."""
    d = os.path.join(root, sha, "figures")
    if os.path.isdir(d):
        for name in os.listdir(d):
            if name.startswith("p%04d-" % page) and name.endswith(".png"):
                os.unlink(os.path.join(d, name))
    if not figs:
        return
    from kb_distillery.storage.pdf import PdfDoc
    os.makedirs(d, exist_ok=True)
    with PdfDoc(pdf) as doc:
        im = doc.render(page - 1, FIG_WIDTH)
    w, h = im.size
    for f in figs:
        if f.get("box"):
            x0, y0, x1, y1 = f["box"]
            crop = im.crop((int(max(0.0, x0 - PAD) * w), int(max(0.0, y0 - PAD) * h),
                            int(min(1.0, x1 + PAD) * w), int(min(1.0, y1 + PAD) * h)))
        else:
            crop = im
        name = "p%04d-%d.png" % (page, f["id"])
        crop.save(os.path.join(d, name))
        f["file"] = name


def _desc_path(work: str, page: int, n: int) -> str:
    return os.path.join(work, "figures", "p%04d-%d.json" % (page, n))


def cached(work: str, page: int, f: dict) -> str | None:
    """A description cached for this very crop (same box, same caption), else None."""
    try:
        with open(_desc_path(work, page, f["id"]), encoding="utf-8") as fh:
            c = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return c.get("description") if c.get("box") == f.get("box") and c.get("caption") == f.get("caption") else None


def describe(figs_by_page: dict, root: str, sha: str, work: str, backend: str | None = None, model: str | None = None,
             force: bool = False, log=print) -> float:
    """Fill `description` of every figure record (cached in `work` per crop); returns the cost in USD (0 on the
    subscription). A reply without the markers is tried once more; a figure still without one stays undescribed."""
    from kb_distillery import llm
    from . import reader
    model = model or reader.MODEL
    todo, usd = [], 0.0
    for p, figs in sorted(figs_by_page.items()):
        for f in figs:
            hit = None if force else cached(work, p, f)
            if hit:
                f["description"] = hit
            elif f.get("file"):
                todo.append((p, f))
    if not todo:
        return 0.0
    backend = llm.resolve_backend(backend)
    for attempt in (1, 2):
        if not todo:
            break
        log("figures: describing %d figure(s), model %s, backend %s" % (len(todo), model, backend))
        reqs = [llm.Request(prompt=DESCRIBE_PROMPT.format(caption=f.get("caption") or "(none)"),
                            id="f%04d-%d" % (p, f["id"]), model=model,
                            images=[os.path.join(root, sha, "figures", f["file"])], max_tokens=DESCRIBE_MAX_TOKENS,
                            effort="low") for p, f in todo]
        again = []
        for (p, f), r in zip(todo, llm.run(reqs, backend=backend)):
            usd += r.usd if backend != "subscription" else 0.0
            text = reply_text(r.text) if r.ok else None
            if text is None:
                again.append((p, f))
                if attempt == 2:
                    log("figures: page %d figure %d not described (%s)" % (p, f["id"], (r.error or "no marked reply")[:120]))
                continue
            f["description"] = text
            path = _desc_path(work, p, f["id"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"box": f.get("box"), "caption": f.get("caption"), "description": text}, fh, ensure_ascii=False)
        todo = again
    return round(usd, 4)


def with_descriptions(text: str, figs: dict) -> str:
    """`text` with each figure link followed by its description as an italic line, for a model that cannot see the
    figure (`figs`: {(sha12, page, id): record})."""
    def add(m):
        f = figs.get((m.group(2), int(m.group(3)), int(m.group(4))))
        d = (f or {}).get("description", "").strip()
        return m.group(0) + ("\n\n*[What the figure shows, described from its image: %s]*" % " ".join(d.split()) if d else "")
    return LINK.sub(add, text)
