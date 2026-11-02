"""Small PDFs built with tests.pdfkit for the verifier tests. Every page has a running head, a page number, prose, inline math
(letters, subscripts, accents drawn as separate raised glyphs, an overline as a ruled line), a theorem, a numbered
display equation, a table and a captioned figure; `PAGES` pairs each with the Markdown a good parser would write."""
from tests import pdfkit

H, M, S = "helv", "heit", 10          # prose font, math (italic) font, size


def put(page, x, y, text, size=S, font=H):
    """Write text at (x, y) on the baseline; return the x after it."""
    page.insert_text((x, y), text, fontsize=size, fontname=font)
    return x + pdfkit.text_length(text, font, size)


def line(page, x, y, parts):
    """parts: ('t', text) prose, ('m', text) math letter, ('s', text) subscript, ('p', text) superscript,
    ('a', accent_char, base_char) a base with a raised accent glyph, ('o', text) text under an overline."""
    for p in parts:
        k = p[0]
        if k == "t":
            x = put(page, x, y, p[1])
        elif k == "m":
            x = put(page, x, y, p[1], font=M)
        elif k == "s":
            x = put(page, x, y + 2.5, p[1], size=7, font=M)
        elif k == "p":
            x = put(page, x, y - 3.5, p[1], size=7, font=M)
        elif k == "a":
            put(page, x + 1.5, y - 6.5, p[1], size=S, font=H)
            x = put(page, x, y, p[2], font=M)
        elif k == "o":
            x1 = put(page, x, y, p[1], font=M)
            page.draw_line((x, y - 9.5), (x1, y - 9.5), width=0.6)
            x = x1
    return x


def frame(page, n, head="Notes on stable maps"):
    put(page, 72, 36, head, size=8)
    put(page, 300, 805, str(n), size=8)


def page1(doc):
    pg = doc.new_page()
    frame(pg, 1)
    put(pg, 72, 90, "2 Preliminaries", size=14, font="hebo")
    line(pg, 72, 120, [("t", "Let "), ("m", "x"), ("t", " be a unit vector and "), ("a", "~", "y"),
                       ("t", " its image. We say the map "), ("m", "f"), ("t", " is stable iff it is bounded,")])
    line(pg, 72, 134, [("t", "and there are 12 samples with 7 outliers in the first batch.")])
    line(pg, 72, 160, [("t", "Theorem 2.1. If "), ("m", "A"), ("t", " is symmetric then "), ("o", "A"),
                       ("t", " is symmetric.")])
    line(pg, 150, 200, [("m", "z"), ("t", " = "), ("m", "x"), ("s", "i"), ("t", " + "), ("m", "y"), ("p", "2"),
                        ("t", "    (2.1)")])
    put(pg, 72, 240, "Table 1. Results")
    for r, row in enumerate((("size", "score"), ("small", "31"), ("large", "58"))):
        for c, cell in enumerate(row):
            put(pg, 80 + c * 90, 262 + r * 16, cell)
    pg.draw_line((72, 252), (260, 252), width=0.5)
    return pg


MD1 = """\
## 2 Preliminaries

Let $x$ be a unit vector and $\\tilde{y}$ its image. We say the map $f$ is stable iff it is bounded,
and there are 12 samples with 7 outliers in the first batch.

**Theorem 2.1.** If $A$ is symmetric then $\\overline{A}$ is symmetric.

$$z = x_i + y^2 \\tag{2.1}$$

Table 1. Results

| size | score |
|---|---|
| small | 31 |
| large | 58 |
"""


def page2(doc):
    pg = doc.new_page()
    frame(pg, 2)
    line(pg, 72, 100, [("t", "Lemma 2.2. For every "), ("m", "n"), ("t", " the quantity "), ("a", "^", "w"),
                       ("t", " is finite, since the series converges.")])
    line(pg, 72, 124, [("t", "Proof. Observe that "), ("a", "·", "u"), ("t", " grows slowly; hence the sum of the"),])
    line(pg, 72, 138, [("t", "decomposition coefficients stays below 40 in every case.")])
    pg.insert_image((100, 170, 220, 250), color=(200, 60, 60))
    put(pg, 72, 270, "Figure 1. A sample curve")
    line(pg, 150, 310, [("m", "u"), ("t", " = "), ("m", "w"), ("s", "k"), ("t", "    (2.2)")])
    return pg


MD2 = """\
**Lemma 2.2.** For every $n$ the quantity $\\hat{w}$ is finite, since the series converges.

*Proof.* Observe that $\\dot{u}$ grows slowly; hence the sum of the
decomposition coefficients stays below 40 in every case.

![](fig1.png)

Figure 1. A sample curve

$$u = w_k \\tag{2.2}$$
"""

def page3(doc):
    pg = doc.new_page()
    frame(pg, 3)
    line(pg, 72, 100, [("t", "Corollary 2.3. A map is bounded if and only if the well-known decompo-")])
    line(pg, 72, 114, [("t", "sition of its graph is finite; see [12] for details on the 3 cases.")])
    line(pg, 150, 150, [("m", "v"), ("t", " = "), ("m", "u"), ("t", " + "), ("m", "x"), ("s", "i"), ("t", "    (2.3)")])
    line(pg, 150, 170, [("t", "|"), ("m", "u"), ("t", "| = |"), ("m", "v"), ("t", "|    (2.4)")])
    put(pg, 72, 190, "Table 2. Timing")
    for r, row in enumerate((("name", "secs"), ("fast", "0.5"), ("slow", "12.5"))):
        for c, cell in enumerate(row):
            put(pg, 80 + c * 90, 212 + r * 16, cell)
    return pg


MD3 = """\
**Corollary 2.3.** A map is bounded if and only if the well-known decomposition of its graph is finite; see [12] for details on the 3 cases.

$$v = u + x_i \\tag{2.3}$$

$$\\left| u \\right| = |v| \\tag{2.4}$$

Table 2. Timing

| name | secs |
|---|---|
| fast | 0.5 |
| slow | 12.5 |
"""

PAGES_MD = [MD1, MD2, MD3]


def build(path=None):
    doc = pdfkit.Doc()
    page1(doc)
    page2(doc)
    page3(doc)
    if path:
        doc.save(path)
    data = doc.tobytes()
    doc.close()
    return data
