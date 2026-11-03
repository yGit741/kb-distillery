import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { drawNode, drawNodeState } from "./canvas";
import { NodeMarkSvg } from "./NodeMarkSvg";
import { GEOMETRY, glyphOf, GLYPH_LABEL, markOf, MARK_KEY, personInitials, STATE, type NodeMark } from "./spec";
import { GLYPH_SVG } from "./spec";

/** A 2D context that records what is drawn: arcs (radius, filled/stroked), lines, text. */
function recorder() {
  const ops: { op: string; r?: number; text?: string; filled?: boolean; stroked?: boolean }[] = [];
  let path: { op: string; r?: number }[] = [];
  const ctx = {
    globalAlpha: 1,
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
    lineCap: "butt",
    lineJoin: "miter",
    font: "",
    textAlign: "start",
    textBaseline: "alphabetic",
    save() {},
    restore() {},
    beginPath() {
      path = [];
    },
    closePath() {},
    arc(_x: number, _y: number, r: number) {
      path.push({ op: "arc", r });
    },
    ellipse() {},
    rect() {
      path.push({ op: "rect" });
    },
    moveTo() {},
    lineTo() {
      path.push({ op: "line" });
    },
    quadraticCurveTo() {
      path.push({ op: "curve" });
    },
    fill() {
      for (const p of path) ops.push({ ...p, filled: true });
    },
    stroke() {
      for (const p of path) ops.push({ ...p, stroked: true });
    },
    fillText(text: string) {
      ops.push({ op: "text", text });
    },
    createRadialGradient() {
      return { addColorStop() {} };
    },
  };
  return { ctx: ctx as unknown as CanvasRenderingContext2D, ops };
}

const draw = (type: string, extra: Partial<Parameters<typeof drawNode>[2]> = {}) => {
  const { ctx, ops } = recorder();
  drawNode(ctx, type, { x: 0, y: 0, r: 10, color: "#123456", background: "#fff", font: "sans", ring: "#00f", initials: "GK", ...extra });
  return ops;
};
const arcs = (ops: ReturnType<typeof draw>) => ops.filter((o) => o.op === "arc");

describe("encoding spec", () => {
  it("gives every type one mark; unknown types are sources", () => {
    expect(markOf("idea")).toBe("idea");
    expect(markOf("question")).toBe("question");
    expect(markOf("topic")).toBe("topic");
    expect(markOf("person")).toBe("person");
    for (const t of ["course", "book", "series", "part"]) expect(markOf(t)).toBe("collection");
    for (const t of ["paper", "article", "blog-post", "ai-chat", "lecture", "video", "mail"]) expect(markOf(t)).toBe("source");
  });

  it("gives every source type and raw format a glyph", () => {
    expect(glyphOf("paper")).toBe("paper");
    expect(glyphOf("ai-chat")).toBe("sparkle");
    expect(glyphOf("conversation")).toBe("mail");
    expect(glyphOf("lecture")).toBe("play");
    expect(glyphOf("part")).toBe("book");
    expect(glyphOf("blog-post")).toBe("text");
    expect(glyphOf("web")).toBe("clip");
    expect(glyphOf("slides")).toBe("slides");
    expect(glyphOf("image")).toBe("image");
    expect(glyphOf("handwritten")).toBe("handwritten");
    // the canvas and the SVG know the same glyphs, each with a legend name
    expect(Object.keys(GLYPH_SVG).sort()).toEqual(Object.keys(GLYPH_LABEL).sort());
  });

  it("takes a person's initials, and a third letter when two people would share them", () => {
    const m = personInitials([
      { id: "gil-karp", type: "person", title: "Gil Karp" },
      { id: "gal-kaplan", type: "person", title: "Gal Kaplan" },
      { id: "nati-linial", type: "person", title: "Nati Linial" },
      { id: "x", type: "idea", title: "Not a person" },
    ]);
    expect(m.get("gil-karp")).toBe("GKa");
    expect(m.get("gal-kaplan")).toBe("GKa");
    expect(m.get("nati-linial")).toBe("NL");
    expect(m.has("x")).toBe(false);
  });
});

describe("drawNode (canvas)", () => {
  it("draws each mark from the shared geometry", () => {
    // source: one filled disc
    expect(arcs(draw("paper"))).toEqual([{ op: "arc", r: 10, filled: true }]);
    // idea: a ring (filled with the background, stroked) and a centre dot
    expect(arcs(draw("idea")).map((o) => o.r)).toEqual([10, 10, 10 * GEOMETRY.ideaDot]);
    // question: a ring and a "?"
    const q = draw("question");
    expect(arcs(q).map((o) => o.r)).toEqual([10, 10]);
    expect(q.find((o) => o.op === "text")?.text).toBe("?");
    // topic: a ring and three lines
    const t = draw("topic");
    expect(arcs(t).map((o) => o.r)).toEqual([10, 10]);
    expect(t.filter((o) => o.op === "line")).toHaveLength(3);
    // collection: an outer ring, then the ring
    expect(arcs(draw("course")).map((o) => o.r)).toEqual([10 * GEOMETRY.collectionOuter, 10, 10]);
    // person: a disc with the initials
    const p = draw("person");
    expect(arcs(p)).toHaveLength(1);
    expect(p.find((o) => o.op === "text")?.text).toBe("GK");
  });

  it("adds a source's glyph only when asked", () => {
    expect(draw("paper").some((o) => o.op === "line")).toBe(false);
    expect(draw("paper", { glyph: true }).some((o) => o.op === "line")).toBe(true);
    // a concept never gets a glyph
    expect(draw("idea", { glyph: true }).filter((o) => o.op === "line")).toHaveLength(0);
  });

  it("draws the selection ring outside the mark and the hover glow wider still", () => {
    const sel = draw("idea", { state: "selected" });
    expect(sel[0]).toEqual({ op: "arc", r: 10 + STATE.gap, stroked: true });
    const hov = draw("idea", { state: "hover" });
    expect(hov[0]).toEqual({ op: "arc", r: 10 + STATE.glow, filled: true });
    // zoomed in: px widths shrink with the zoom
    const { ctx, ops } = recorder();
    drawNodeState(ctx, "selected", 0, 0, 10, "#000", "#00f", 2);
    expect(ops[0]!.r).toBe(10 + STATE.gap / 2);
  });
});

describe("NodeMarkSvg", () => {
  const svg = (type: string) => render(<NodeMarkSvg type={type} />).container.querySelector("svg")!;
  const circles = (type: string) => svg(type).querySelectorAll("circle").length;

  it("draws the same mark as the canvas for every type", () => {
    const expected: Record<NodeMark, number> = { source: 1, person: 1, question: 1, idea: 2, topic: 1, collection: 2 };
    const sample: Record<NodeMark, string> = { source: "", person: "person", question: "question", idea: "idea", topic: "topic", collection: "course" };
    for (const { mark } of MARK_KEY) {
      if (mark === "source") continue;
      expect(circles(sample[mark]), mark).toBe(expected[mark]);
    }
    expect(svg("question").textContent).toBe("?");
    expect(svg("topic").querySelector("path")).not.toBeNull();
    // a source is its glyph
    expect(svg("paper").querySelector("path")?.getAttribute("d")).toBe(GLYPH_SVG.paper.d);
    expect(svg("lecture").querySelector("path")?.getAttribute("d")).toBe(GLYPH_SVG.play.d);
  });
});
