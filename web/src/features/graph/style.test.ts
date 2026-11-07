import type { GNode } from "./types";
import { node } from "./fixtures";
import { AREA_PALETTE, areaHue, assignAreaColors, colorKey, colorOf, layeredRadii, nodeRadius, NONE_GREY, OTHER_GREY } from "./style";
import { RING_BOOST } from "./encoding/spec";
import { TYPE_COLORS, DEPTH_COLORS, LAYER_COLORS, UNKNOWN_COLOR } from "@/theme/palette";

describe("colorOf", () => {
  const paper = node("p", { type: "paper", layer: "source", depth: "deep", status: "digested", areas: ["info-theory"], inDegree: 7, outDegree: 6 });
  it("takes colours from the one data palette", () => {
    expect(colorOf(paper, "type")).toBe(TYPE_COLORS.paper);
    expect(colorOf(paper, "layer")).toBe(LAYER_COLORS.source);
    expect(colorOf(paper, "depth")).toBe(DEPTH_COLORS.deep);
    expect(colorOf(node("c"), "depth")).toBe(UNKNOWN_COLOR);
  });
  it("bands the link count", () => {
    expect(colorOf(paper, "degree")).toBe("#ff6b7a");
    expect(colorKey(paper, "degree")).toBe("12+ links");
    expect(colorKey(node("z"), "degree")).toBe("0–1 links");
  });
  it("names the key per colouring", () => {
    expect(colorKey(paper, "depth")).toBe("deep");
    expect(colorKey(node("c"), "depth")).toBe("(not a source)");
    assignAreaColors([paper]);
    expect(colorKey(paper, "area")).toBe("Information theory");
    expect(colorKey(node("o", { areas: ["quantum"] }), "area")).toBe("Other areas");
    expect(colorKey(node("n", { areas: [] }), "area")).toBe("No area");
    expect(colorKey(node("c"), "status")).toBe("growing");
    expect(colorKey(node("c"), "none")).toBe("All pages");
  });
});

describe("area colours", () => {
  it("give the largest areas the palette in order, grey past it and for none", () => {
    const pages = [
      ...Array.from({ length: 3 }, (_, i) => node(`a${i}`, { areas: ["big"] })),
      ...Array.from({ length: 2 }, (_, i) => node(`b${i}`, { areas: ["mid"] })),
      ...Array.from({ length: 13 }, (_, i) => node(`s${i}`, { areas: [`small-${String(i).padStart(2, "0")}`] })),
    ];
    assignAreaColors(pages);
    expect(areaHue("big")).toBe(AREA_PALETTE[0]);
    expect(areaHue("mid")).toBe(AREA_PALETTE[1]);
    expect(areaHue("small-12")).toBe(OTHER_GREY);
    expect(areaHue("")).toBe(NONE_GREY);
  });
});

describe("layeredRadii", () => {
  it("keeps ideas at least the median paper, people at least the idea median, topics at least the largest idea", () => {
    const pages = [
      node("p1", { type: "paper", layer: "source", depth: "deep", inDegree: 20 }),
      node("p2", { type: "paper", layer: "source", depth: "deep", inDegree: 20 }),
      node("p3", { type: "paper", layer: "source", depth: "deep", inDegree: 20 }),
      node("i1", { type: "idea", layer: "concept", inDegree: 0 }),
      node("i2", { type: "idea", layer: "concept", inDegree: 40 }),
      node("pe", { type: "person", layer: "concept", inDegree: 0 }),
      node("t", { type: "topic", layer: "concept", inDegree: 0 }),
    ];
    const r = layeredRadii(pages, { by: "connections", base: 5 });
    const paper = r.get("p1")!;
    expect(r.get("i1")!).toBeGreaterThanOrEqual(paper);
    expect(r.get("pe")!).toBeGreaterThanOrEqual(r.get("i1")! / RING_BOOST);
    expect(r.get("t")!).toBeGreaterThanOrEqual(r.get("i2")!);
    // sources stay under the typical idea
    expect(paper).toBeLessThanOrEqual(r.get("i2")!);
  });
});

describe("nodeRadius", () => {
  const base = { by: "connections" as const, base: 5 };
  it("grows with links through a square root and caps at 24", () => {
    const r0 = nodeRadius(node("a"), base);
    const r3 = nodeRadius(node("a", { inDegree: 3 }), base);
    const r24 = nodeRadius(node("a", { inDegree: 24 }), base);
    const r99 = nodeRadius(node("a", { inDegree: 99 }), base);
    expect(r0).toBeCloseTo(3);
    expect(r3).toBeGreaterThan(r0);
    expect(r24).toBeCloseTo(8);
    expect(r99).toBe(r24);
    expect((r3 - r0) / 3).toBeGreaterThan((r24 - r3) / 21); // concave: the first links count most
  });
  it("draws a collection as a larger hub", () => {
    const m = node("c", { layer: "collection", type: "course", inDegree: 2 });
    expect(nodeRadius(m, base)).toBeCloseTo(nodeRadius(node("c", { inDegree: 2 }), base) * 1.5);
  });
  it("uniform ignores links; in/out pick one direction", () => {
    const n = node("a", { inDegree: 10, outDegree: 0 });
    expect(nodeRadius(n, { by: "uniform", base: 4 })).toBe(4);
    expect(nodeRadius(n, { by: "out", base: 5 })).toBeCloseTo(3);
    expect(nodeRadius(n, { by: "in", base: 5 })).toBeGreaterThan(3);
  });
});

describe("lab size and colour modes", () => {
  it("tier sizes topics above ideas above sources", () => {
    const o = { by: "tier" as const, base: 4, range: 2 };
    expect(nodeRadius(node("t", { type: "topic" }), o)).toBeGreaterThan(nodeRadius(node("i", { type: "idea" }), o));
    expect(nodeRadius(node("p", { type: "paper", layer: "source" }), o)).toBe(4);
  });
  it("metric modes read the importance signal, with perceptual scaling", () => {
    const o = { by: "evidence" as const, base: 4, range: 2, metric: () => 0.25 };
    expect(nodeRadius(node("a"), o)).toBeCloseTo(4 * (1 + 2 * 0.25));
    expect(nodeRadius(node("a"), { ...o, perceptual: true })).toBeCloseTo(4 * (1 + 2 * Math.pow(0.25, 0.57)));
  });
  it("evidence colour is grey without a signal and sequential with one", () => {
    expect(colorOf(node("a"), "evidence")).toBe(UNKNOWN_COLOR);
    expect(colorOf(node("a"), "evidence", 1)).toBe("rgb(31, 91, 214)");
  });
});

describe("a kb without areas (an imported OKF bundle)", () => {
  it("colours by page type under the area colouring, and keys the legend by type", async () => {
    const { areaSlots, assignAreaColors, colorKey, colorOf } = await import("./style");
    const node = (id: string, type: string, areas: string[] = []): GNode => ({ id, type, areas, layer: "", depth: "", maturity: "" }) as unknown as GNode;
    const concept = node("a", "Concept");
    const source = node("b", "Source");
    assignAreaColors([concept, source, node("c", "Source")]);
    expect(colorKey(source, "area")).toBe("Source");
    expect(colorOf(source, "area")).not.toBe(colorOf(concept, "area"));
    // slots a surface builds itself (Home, the mini graph) decide on their own pages, never on the last graph shown
    const loose = node("y", "concept");
    const withAreas = areaSlots([node("x", "concept", ["math"]), loose]);
    expect(colorKey(loose, "area", withAreas)).toBe("No area");
    expect(colorKey(source, "area", areaSlots([concept, source]))).toBe("Source");
    // and the Full Graph of a kb with areas keeps its pages without one grey
    assignAreaColors([node("x", "concept", ["math"]), loose]);
    expect(colorKey(loose, "area")).toBe("No area");
  });
});
